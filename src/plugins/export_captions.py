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
        mode_group = QGroupBox("Binning Options")
        mode_layout = QVBoxLayout(mode_group)

        self.bin_by_repeats_check = QCheckBox("Bin by repeats")
        self.bin_by_trigger_check = QCheckBox("Bin by number of trigger words")
        self.bin_by_duration_check = QCheckBox("Bin by duration (videos)")

        # Trigger category input
        trigger_layout = QHBoxLayout()
        trigger_layout.addWidget(QLabel("Trigger Category:"))
        self.trigger_category_input = QLineEdit("trigger")
        trigger_layout.addWidget(self.trigger_category_input)

        # Duration bins input
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Duration Bins (sec):"))
        self.duration_bins_input = QLineEdit("1,2,5,10")
        duration_layout.addWidget(self.duration_bins_input)

        mode_layout.addWidget(self.bin_by_repeats_check)
        mode_layout.addLayout(trigger_layout)
        mode_layout.addWidget(self.bin_by_trigger_check)
        mode_layout.addWidget(self.bin_by_duration_check)
        mode_layout.addLayout(duration_layout)

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

        self.duplicate_by_repeats_check = QCheckBox("Duplicate media by repeat count")
        options_layout.addWidget(self.duplicate_by_repeats_check)

        self.export_zero_repeats_check = QCheckBox(
            "Export zero repeats (export all images even if they have zero repeats)"
        )
        options_layout.addWidget(self.export_zero_repeats_check)

        self.kohya_toml_check = QCheckBox("Create Kohya TOML config file")
        options_layout.addWidget(self.kohya_toml_check)

        # Connect checkbox handlers
        self.bin_by_repeats_check.toggled.connect(
            lambda checked: self.duplicate_by_repeats_check.setDisabled(checked)
        )
        self.bin_by_trigger_check.toggled.connect(
            lambda checked: self.trigger_category_input.setEnabled(checked)
        )
        self.bin_by_duration_check.toggled.connect(
            lambda checked: self.duration_bins_input.setEnabled(checked)
        )

        # Initial states
        self.trigger_category_input.setEnabled(False)
        self.duration_bins_input.setEnabled(False)

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

        # Determine export options
        is_bin_by_repeats = self.bin_by_repeats_check.isChecked()
        is_bin_by_trigger = self.bin_by_trigger_check.isChecked()
        is_bin_by_duration = self.bin_by_duration_check.isChecked()

        trigger_category = self.trigger_category_input.text().strip()
        duration_bins_str = self.duration_bins_input.text().strip()

        # Parse duration bins
        duration_bins = []
        if is_bin_by_duration and duration_bins_str:
            try:
                duration_bins = [
                    float(b.strip()) for b in duration_bins_str.split(",") if b.strip()
                ]
                duration_bins.sort()
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid Bins",
                    "Invalid duration bins. Use comma-separated numbers.",
                )
                return

        use_symlinks = self.symlink_check.isChecked()
        duplicate_by_repeats = (
            self.duplicate_by_repeats_check.isChecked() and not is_bin_by_repeats
        )
        create_kohya_toml = self.kohya_toml_check.isChecked()
        export_zero_repeats = self.export_zero_repeats_check.isChecked()

        # Export images
        try:
            print(f"DEBUG: Starting export with bins: {duration_bins}")
            exported_count = self._do_export(
                working_images,
                output_dir,
                active_profile,
                is_bin_by_repeats,
                is_bin_by_trigger,
                is_bin_by_duration,
                trigger_category,
                duration_bins,
                use_symlinks,
                duplicate_by_repeats,
                create_kohya_toml,
                export_zero_repeats,
            )

            msg = f"Exported {exported_count} image(s) to {output_dir}"
            if create_kohya_toml:
                msg += f"\n\nKohya TOML config saved to {output_dir / 'config.toml'}"

            QMessageBox.information(self, "Export Complete", msg)
        except Exception as e:
            import traceback

            traceback.print_exc()
            QMessageBox.critical(self, "Export Error", f"Error during export: {e}")

    def _do_export(
        self,
        images: List[Path],
        output_dir: Path,
        active_profile: str,
        is_bin_by_repeats: bool,
        is_bin_by_trigger: bool,
        is_bin_by_duration: bool,
        trigger_category: str,
        duration_bins: List[float],
        use_symlinks: bool,
        duplicate_by_repeats: bool,
        create_kohya_toml: bool,
        export_zero_repeats: bool = False,
    ) -> int:
        """Perform the actual export operation"""
        exported_count = 0
        project = self.app_manager.get_project()

        # Parse active profile if provided
        template_parts = None
        if active_profile:
            try:
                template_parts = parse_export_template(active_profile)
            except Exception as e:
                print(f"Error parsing active profile: {e}")

        # Group images for binning
        groups = {}  # folder_name -> [img_paths]

        # If no binning, everything goes to root or is grouped by empty string
        for img_path in images:
            repeat_count = project.image_list.get_repeat(img_path)

            # Skip zero repeats unless export_zero_repeats is enabled
            if repeat_count == 0 and not export_zero_repeats:
                continue

            folder_parts = []

            # 1. Repeats
            if is_bin_by_repeats:
                folder_parts.append(f"{repeat_count}_repeats")

            # Load image data once if needed for triggers or duration
            img_data = None
            if is_bin_by_trigger or is_bin_by_duration:
                img_data = self.app_manager.load_image_data(img_path)

            # 2. Triggers
            if is_bin_by_trigger and img_data:
                trigger_tags = img_data.get_tags_by_category(trigger_category)
                trigger_count = len(trigger_tags)
                folder_parts.append(f"{trigger_count}_triggers")

            # 3. Duration
            if is_bin_by_duration and img_data:
                duration = img_data.metadata.get("duration", 0.0)
                try:
                    duration = float(duration)
                except (ValueError, TypeError):
                    duration = 0.0

                from ..utils import get_nearest_bin

                duration_bin = get_nearest_bin(duration, duration_bins)
                folder_parts.append(f"{int(duration_bin)}s")

                if duration > 0:
                    print(
                        f"DEBUG: {img_path.name} - duration: {duration:.2f}s, binned to: {int(duration_bin)}s"
                    )
                else:
                    print(
                        f"DEBUG: {img_path.name} - duration NOT FOUND (0.0s), binned to: {int(duration_bin)}s"
                    )

            folder_name = "_".join(folder_parts) if folder_parts else ""

            if folder_name not in groups:
                groups[folder_name] = []
            groups[folder_name].append(img_path)

        # Export groups
        for folder_name, img_paths in groups.items():
            dest_dir = output_dir / folder_name
            dest_dir.mkdir(parents=True, exist_ok=True)

            for img_path in img_paths:
                # Handle duplication by repeats
                num_copies = (
                    project.image_list.get_repeat(img_path)
                    if duplicate_by_repeats
                    else 1
                )
                if num_copies <= 0:
                    num_copies = 1  # Safety

                for i in range(num_copies):
                    suffix = f"_{i + 1}" if num_copies > 1 else ""
                    dest_stem = img_path.stem + suffix
                    dest_name = dest_stem + img_path.suffix

                    exported_count += self._export_single_image(
                        img_path,
                        dest_dir,
                        dest_name,
                        template_parts,
                        use_symlinks,
                    )

        # Create Kohya TOML if requested
        if create_kohya_toml:
            self._create_kohya_toml_new(
                output_dir,
                groups,
                is_bin_by_repeats,
                is_bin_by_trigger,
                is_bin_by_duration,
                trigger_category,
                duration_bins,
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

    def _create_kohya_toml_new(
        self,
        output_dir: Path,
        groups: dict,
        is_bin_by_repeats: bool,
        is_bin_by_trigger: bool,
        is_bin_by_duration: bool,
        trigger_category: str,
        duration_bins: List[float],
    ):
        """Create Kohya TOML configuration file for the new structure"""
        project = self.app_manager.get_project()

        # Load template and subset template
        template = project.export.get("kohya_template", self.DEFAULT_KOHYA_TEMPLATE)
        subset_template = project.export.get(
            "kohya_subset_template", self.DEFAULT_KOHYA_SUBSET_TEMPLATE
        )

        # Generate TOML subset entries
        subset_entries = []
        for folder_name in sorted(groups.keys()):
            if not folder_name:
                image_dir = "."
            else:
                image_dir = folder_name

            # We need to extract num_repeats and keep_tokens from the folder name or images
            # Since a group might have different repeats if not binning by repeats,
            # this is tricky for Kohya TOML which expects per-folder repeats.
            # However, if we are NOT binning by repeats, we probably just use 1.

            # Pick first image in group to get its repeat count
            first_img = groups[folder_name][0]
            repeat_count = project.image_list.get_repeat(first_img)

            # If binning by trigger, get trigger count from first image
            trigger_count = 0
            if is_bin_by_trigger:
                img_data = self.app_manager.load_image_data(first_img)
                trigger_count = len(img_data.get_tags_by_category(trigger_category))

            # Apply subset template
            entry = subset_template.replace("{{image_dir}}", image_dir)
            entry = entry.replace(
                "{{num_repeats}}", str(repeat_count if is_bin_by_repeats else 1)
            )

            # Handle keep_tokens placeholder
            if is_bin_by_trigger:
                if (
                    "keep_tokens" not in entry
                    and "{{tokens_no}}" not in subset_template
                ):
                    entry = entry.rstrip() + f"\n    keep_tokens = {trigger_count}\n"
                else:
                    entry = entry.replace("{{tokens_no}}", str(trigger_count))
            else:
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
