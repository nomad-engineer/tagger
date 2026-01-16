"""
Export Captions Plugin - Export caption files with advanced options
"""

import shutil
from typing import List
from pathlib import Path
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QMessageBox,
    QWidget,
    QRadioButton,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QDialog,
    QDialogButtonBox,
)
from PyQt5.QtCore import Qt

from ..plugin_base import PluginWindow
from ..utils import parse_export_template, apply_export_template


class ExportCaptionsPlugin(PluginWindow):
    """Plugin to export images and captions with various options"""

    # Default Kohya TOML template
    DEFAULT_KOHYA_TEMPLATE = """[general]
shuffle_caption = true
caption_extension = '.txt'
keep_tokens = 1

[[datasets]]
resolution = [1024, 1024]
min_bucket_reso = 256
max_bucket_reso = 2048
enable_bucket = true

    {{SUBSETS}}

    #---reg----------------------

    [[datasets.subsets]]
    image_dir = "images_reg/animals"
    num_repeats = 1
    is_reg = true
"""

    DEFAULT_KOHYA_SUBSET_TEMPLATE = """    [[datasets.subsets]]
    image_dir = "{{image_dir}}"
    num_repeats = {{num_repeats}}
"""

    def __init__(self, app_manager, parent=None):
        super().__init__(app_manager, parent)

        self.name = "Export"
        self.description = "Export images and captions"
        self.shortcut = "Ctrl+E"

        self.setWindowTitle(self.name)
        self.resize(700, 600)

        self._setup_ui()

        # Connect to signals
        self.app_manager.project_changed.connect(self._update_ui)
        self.app_manager.library_changed.connect(self._update_ui)

        # Initial load
        self._update_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Instructions
        instructions = QLabel(
            "Export images and their captions to a directory.\n"
            "Uses the active caption profile from the Caption Profile plugin."
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(instructions)

        # Active profile display
        self.active_profile_label = QLabel()
        self.active_profile_label.setStyleSheet("color: green; font-weight: bold;")
        self.active_profile_label.setWordWrap(True)
        layout.addWidget(self.active_profile_label)

        # Export mode section
        mode_group = QGroupBox("Export Structure")
        mode_layout = QVBoxLayout(mode_group)

        self.mode_group = QButtonGroup(self)
        self.flat_radio = QRadioButton("Flat: All images in the same folder")
        self.relative_radio = QRadioButton(
            "Relative: Using relative paths as in project"
        )
        self.bin_by_repeats_radio = QRadioButton(
            "Bin by repeats: Folder per repeat count (e.g., 2_repeats)"
        )
        self.flat_radio.setChecked(True)

        # Bin by trigger words option
        self.bin_by_trigger_check = QCheckBox("Bin by number of trigger words")
        self.bin_by_trigger_check.setEnabled(False)
        self.trigger_category_input = QLineEdit("trigger")
        self.trigger_category_input.setEnabled(False)
        self.bin_by_trigger_check.stateChanged.connect(
            lambda state: self.trigger_category_input.setEnabled(
                state == 2
            )  # 2 is Qt.Checked
        )

        self.mode_group.addButton(self.flat_radio)
        self.mode_group.addButton(self.relative_radio)
        self.mode_group.addButton(self.bin_by_repeats_radio)

        self.bin_by_repeats_radio.toggled.connect(
            lambda checked: self.bin_by_trigger_check.setEnabled(checked)
        )

        mode_layout.addWidget(self.flat_radio)
        mode_layout.addWidget(self.relative_radio)
        mode_layout.addWidget(self.bin_by_repeats_radio)

        # Trigger binning UI
        trigger_layout = QHBoxLayout()
        trigger_layout.setContentsMargins(20, 0, 0, 0)
        trigger_layout.addWidget(self.bin_by_trigger_check)
        trigger_layout.addWidget(QLabel("Category:"))
        trigger_layout.addWidget(self.trigger_category_input)
        mode_layout.addLayout(trigger_layout)

        layout.addWidget(mode_group)

        # Directory selection
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Output Directory:"))
        self.directory_input = QLineEdit()
        dir_layout.addWidget(self.directory_input)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_directory)
        dir_layout.addWidget(self.browse_btn)

        layout.addLayout(dir_layout)

        # Options section
        options_group = QGroupBox("Export Options")
        options_layout = QVBoxLayout(options_group)

        self.symlink_check = QCheckBox("Create symlinks instead of copying images")
        options_layout.addWidget(self.symlink_check)

        self.export_zero_repeats_check = QCheckBox(
            "Export zero repeats (export all images even if they have zero repeats)"
        )
        options_layout.addWidget(self.export_zero_repeats_check)

        self.kohya_toml_check = QCheckBox("Create Kohya TOML config file")
        options_layout.addWidget(self.kohya_toml_check)

        # Template editor button (for Kohya mode)
        template_layout = QHBoxLayout()
        template_layout.addStretch()
        self.edit_template_btn = QPushButton("Edit TOML Template")
        self.edit_template_btn.clicked.connect(self._edit_template)
        self.edit_template_btn.setEnabled(False)
        template_layout.addWidget(self.edit_template_btn)

        self.edit_subset_template_btn = QPushButton("Edit Subset Template")
        self.edit_subset_template_btn.clicked.connect(self._edit_subset_template)
        self.edit_subset_template_btn.setEnabled(False)
        template_layout.addWidget(self.edit_subset_template_btn)

        options_layout.addLayout(template_layout)

        layout.addWidget(options_group)

        # Connect checkbox handlers
        self.kohya_toml_check.stateChanged.connect(self._on_kohya_check_changed)

        # Export button
        export_layout = QHBoxLayout()
        export_layout.addStretch()
        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self._export_images)
        export_layout.addWidget(self.export_btn)
        layout.addLayout(export_layout)

    def _on_kohya_check_changed(self, state):
        """Handle Kohya checkbox change"""
        is_enabled = state == 2  # 2 is Qt.Checked
        self.edit_template_btn.setEnabled(is_enabled)
        self.edit_subset_template_btn.setEnabled(is_enabled)

    def _update_ui(self):
        """Update UI with current active profile"""
        project = self.app_manager.get_project()
        if not project.project_file:
            self.active_profile_label.setText(
                "Active Profile: None (No project loaded)"
            )
            return

        active_profile = project.export.get("active_caption_profile", "")
        if active_profile:
            self.active_profile_label.setText(
                f"Active Caption Profile: {active_profile}"
            )
        else:
            self.active_profile_label.setText(
                "Active Caption Profile: None (Configure in Caption Profile plugin)"
            )

    def _browse_directory(self):
        """Browse for output directory"""
        # Use persistent file dialog
        directory = self.app_manager.get_existing_directory(
            self, "Select Output Directory", "export"
        )
        if directory:
            self.directory_input.setText(str(directory))

    def _edit_template(self):
        """Open dialog to edit Kohya TOML template"""
        project = self.app_manager.get_project()

        # Get current template or use default
        current_template = project.export.get(
            "kohya_template", self.DEFAULT_KOHYA_TEMPLATE
        )

        # Create dialog
        from PyQt5.QtWidgets import QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Kohya TOML Template")
        dialog.resize(600, 400)

        layout = QVBoxLayout(dialog)

        # Instructions
        instructions = QLabel(
            "Edit the TOML template. Use {{SUBSETS}} as a placeholder where\n"
            "the generated subset entries should be inserted."
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(instructions)

        # Text editor
        text_edit = QTextEdit()
        text_edit.setPlainText(current_template)
        text_edit.setFontFamily("monospace")
        layout.addWidget(text_edit)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog and save if accepted
        if dialog.exec_() == QDialog.Accepted:
            new_template = text_edit.toPlainText()
            project.export["kohya_template"] = new_template
            self.app_manager.update_project(save=True)

    def _edit_subset_template(self):
        """Open dialog to edit Kohya TOML subset template"""
        project = self.app_manager.get_project()

        # Get current template or use default
        current_template = project.export.get(
            "kohya_subset_template", self.DEFAULT_KOHYA_SUBSET_TEMPLATE
        )

        # Create dialog
        from PyQt5.QtWidgets import QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Kohya TOML Subset Template")
        dialog.resize(600, 400)

        layout = QVBoxLayout(dialog)

        # Instructions
        instructions = QLabel(
            "Edit the subset entry template. Available placeholders:\n"
            "{{image_dir}}, {{num_repeats}}, {{tokens_no}}"
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(instructions)

        # Text editor
        text_edit = QTextEdit()
        text_edit.setPlainText(current_template)
        text_edit.setFontFamily("monospace")
        layout.addWidget(text_edit)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog and save if accepted
        if dialog.exec_() == QDialog.Accepted:
            new_template = text_edit.toPlainText()
            project.export["kohya_subset_template"] = new_template
            self.app_manager.update_project(save=True)

    def _export_images(self):
        """Export images and captions to directory"""
        # Get selected images
        working_images = self.get_selected_images()

        if not working_images:
            QMessageBox.warning(self, "No Images", "No images selected.")
            return

        # Check if we need to include zero-repeat images
        export_zero_repeats = self.export_zero_repeats_check.isChecked()
        if export_zero_repeats:
            # Get all images from project to ensure we include zero-repeat images
            all_images = self.get_all_images()
            if all_images:
                working_images = all_images

        # Validate output directory
        output_dir = Path(self.directory_input.text().strip())
        if not output_dir or not str(output_dir):
            QMessageBox.warning(
                self, "No Directory", "Please select an output directory."
            )
            return

        # Create output directory if needed
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get active caption profile
        project = self.app_manager.get_project()
        active_profile = project.export.get("active_caption_profile", "")

        # Determine export mode
        is_flat = self.flat_radio.isChecked()
        is_relative = self.relative_radio.isChecked()
        is_bin_by_repeats = self.bin_by_repeats_radio.isChecked()

        is_bin_by_trigger = self.bin_by_trigger_check.isChecked()
        trigger_category = self.trigger_category_input.text().strip()

        use_symlinks = self.symlink_check.isChecked()
        create_kohya_toml = self.kohya_toml_check.isChecked()
        export_zero_repeats = self.export_zero_repeats_check.isChecked()

        # Export images
        try:
            exported_count = self._do_export(
                working_images,
                output_dir,
                active_profile,
                is_flat,
                is_relative,
                is_bin_by_repeats,
                is_bin_by_trigger,
                trigger_category,
                use_symlinks,
                create_kohya_toml,
                export_zero_repeats,
            )

            msg = f"Exported {exported_count} image(s) to {output_dir}"
            if create_kohya_toml:
                msg += f"\n\nKohya TOML config saved to {output_dir / 'config.toml'}"

            QMessageBox.information(self, "Export Complete", msg)
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Error during export: {e}")

    def _do_export(
        self,
        images: List[Path],
        output_dir: Path,
        active_profile: str,
        is_flat: bool,
        is_relative: bool,
        is_bin_by_repeats: bool,
        is_bin_by_trigger: bool,
        trigger_category: str,
        use_symlinks: bool,
        create_kohya_toml: bool,
        export_zero_repeats: bool = False,
    ) -> int:
        """Perform the actual export operation"""
        exported_count = 0
        project = self.app_manager.get_project()
        base_dir = project.get_base_directory()

        # Parse active profile if provided
        template_parts = None
        if active_profile:
            try:
                template_parts = parse_export_template(active_profile)
            except Exception as e:
                print(f"Error parsing active profile: {e}")

        # Handle binning modes
        if is_bin_by_repeats or is_bin_by_trigger:
            # Group images
            groups = {}  # (repeat_count, trigger_count) -> [img_paths]
            for img_path in images:
                repeat_count = project.image_list.get_repeat(img_path)

                trigger_count = 0
                if is_bin_by_trigger:
                    img_data = self.app_manager.load_image_data(img_path)
                    trigger_tags = img_data.get_tags_by_category(trigger_category)
                    trigger_count = len(trigger_tags)

                group_key = (repeat_count, trigger_count)
                if group_key not in groups:
                    groups[group_key] = []
                groups[group_key].append(img_path)

            # Export each group to its own folder
            for (repeat_count, trigger_count), img_paths in groups.items():
                # Skip zero repeats unless export_zero_repeats is enabled
                if is_bin_by_repeats and repeat_count == 0 and not export_zero_repeats:
                    continue

                # Determine folder name
                if is_bin_by_repeats and is_bin_by_trigger:
                    subset_name = f"{repeat_count}_repeats_{trigger_count}_trigger"
                elif is_bin_by_repeats:
                    subset_name = f"{repeat_count}_repeats"
                else:  # is_bin_by_trigger
                    subset_name = f"{trigger_count}_trigger"

                subset_dir = output_dir / subset_name
                subset_dir.mkdir(parents=True, exist_ok=True)

                for img_path in img_paths:
                    exported_count += self._export_single_image(
                        img_path,
                        subset_dir,
                        img_path.name,
                        template_parts,
                        use_symlinks,
                    )

            # Create Kohya TOML if requested
            if create_kohya_toml:
                self._create_kohya_toml(
                    output_dir, groups, is_bin_by_repeats, is_bin_by_trigger
                )

        elif is_relative and base_dir:
            # Maintain relative path structure
            for img_path in images:
                repeat_count = project.image_list.get_repeat(img_path)
                # Skip zero repeats unless export_zero_repeats is enabled
                if repeat_count == 0 and not export_zero_repeats:
                    continue

                try:
                    rel_path = img_path.relative_to(base_dir)
                    dest_dir = output_dir / rel_path.parent
                    dest_dir.mkdir(parents=True, exist_ok=True)

                    exported_count += self._export_single_image(
                        img_path, dest_dir, img_path.name, template_parts, use_symlinks
                    )
                except ValueError:
                    # Image is outside base_dir, fall back to flat export
                    exported_count += self._export_single_image(
                        img_path,
                        output_dir,
                        img_path.name,
                        template_parts,
                        use_symlinks,
                    )

        else:
            # Flat structure
            for img_path in images:
                repeat_count = project.image_list.get_repeat(img_path)
                # Skip zero repeats unless export_zero_repeats is enabled
                if repeat_count == 0 and not export_zero_repeats:
                    continue

                exported_count += self._export_single_image(
                    img_path, output_dir, img_path.name, template_parts, use_symlinks
                )

        return exported_count

    def _export_single_image(
        self,
        img_path: Path,
        dest_dir: Path,
        dest_name: str,
        template_parts,
        use_symlinks: bool,
    ) -> int:
        """Export a single image and its caption"""
        try:
            # Load image data
            img_data = self.app_manager.load_image_data(img_path)

            # Determine destination paths
            img_dest_path = dest_dir / dest_name
            caption_path = dest_dir / f"{Path(dest_name).stem}.txt"

            # Copy or symlink image
            if use_symlinks:
                # Remove existing symlink if present
                if img_dest_path.is_symlink() or img_dest_path.exists():
                    img_dest_path.unlink()
                img_dest_path.symlink_to(img_path.resolve())
            else:
                shutil.copy2(img_path, img_dest_path)

            # Generate and write caption
            if template_parts:
                caption = apply_export_template(template_parts, img_data)
            else:
                # Use caption from image data if no profile
                caption = img_data.caption

            with open(caption_path, "w") as f:
                f.write(caption if caption else "")

            return 1

        except Exception as e:
            print(f"Error exporting {img_path}: {e}")
            return 0

    def _create_kohya_toml(
        self,
        output_dir: Path,
        groups: dict,
        is_bin_by_repeats: bool,
        is_bin_by_trigger: bool,
    ):
        """Create Kohya TOML configuration file"""
        project = self.app_manager.get_project()

        # Load template and subset template
        template = project.export.get("kohya_template", self.DEFAULT_KOHYA_TEMPLATE)
        subset_template = project.export.get(
            "kohya_subset_template", self.DEFAULT_KOHYA_SUBSET_TEMPLATE
        )

        # Generate TOML subset entries
        subset_entries = []
        for repeat_count, trigger_count in sorted(groups.keys()):
            # Adjust path based on export mode
            if is_bin_by_repeats and is_bin_by_trigger:
                image_dir = f"{repeat_count}_repeats_{trigger_count}_trigger"
            elif is_bin_by_repeats:
                image_dir = f"{repeat_count}_repeats"
            elif is_bin_by_trigger:
                image_dir = f"{trigger_count}_trigger"
            else:
                image_dir = "images"

            # Apply subset template
            entry = subset_template.replace("{{image_dir}}", image_dir)
            entry = entry.replace("{{num_repeats}}", str(repeat_count))

            # Handle keep_tokens placeholder
            if is_bin_by_trigger:
                # If bin by trigger is on and template doesn't have keep_tokens, add it automatically
                if (
                    "keep_tokens" not in entry
                    and "{{tokens_no}}" not in subset_template
                ):
                    entry = entry.rstrip() + f"\n    keep_tokens = {trigger_count}\n"
                else:
                    entry = entry.replace("{{tokens_no}}", str(trigger_count))
            else:
                # Remove tokens_no if not binning by trigger
                entry = entry.replace("{{tokens_no}}", "0")

            subset_entries.append(entry)

        # Combine all subset entries
        subsets_text = "\n".join(subset_entries)

        # Replace placeholder in main template
        final_toml = template.replace("{{SUBSETS}}", subsets_text)

        # Write TOML file
        toml_path = output_dir / "config.toml"
        with open(toml_path, "w") as f:
            f.write(final_toml)
