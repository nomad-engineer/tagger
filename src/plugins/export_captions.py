"""
Export Captions Plugin - Export caption files with advanced options
"""
import shutil
from typing import List
from pathlib import Path
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QTextEdit, QMessageBox, QWidget, QRadioButton,
    QButtonGroup, QCheckBox, QFileDialog, QGroupBox, QDialog, QDialogButtonBox
)
from PyQt5.QtCore import Qt

from ..plugin_base import PluginWindow
from ..utils import parse_export_template, apply_export_template


class ExportCaptionsPlugin(PluginWindow):
    """Plugin to export caption files with various options"""

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

    def __init__(self, app_manager, parent=None):
        super().__init__(app_manager, parent)

        self.name = "Export Captions"
        self.description = "Export caption files for images"
        self.shortcut = "Ctrl+E"

        self.setWindowTitle(self.name)
        self.resize(700, 600)

        self._setup_ui()

        # Connect to signals
        self.app_manager.project_changed.connect(self._load_saved_profiles)
        self.app_manager.project_changed.connect(self._update_preview)

        # Initial load
        self._load_saved_profiles()
        self._update_preview()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Instructions
        instructions = QLabel(
            "Export profile format: trigger, {class}, {camera}, {details}[0:3]\n"
            "{category} = all tags from category, {category}[0:3] = first 3 tags"
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(instructions)

        # Profile string entry
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Export Profile:"))

        self.profile_input = QLineEdit()
        self.profile_input.setPlaceholderText("trigger, {class}, {camera}")
        self.profile_input.textChanged.connect(self._update_preview)
        profile_layout.addWidget(self.profile_input)

        layout.addLayout(profile_layout)

        # Save profile button
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        save_btn = QPushButton("Save Profile")
        save_btn.clicked.connect(self._save_profile)
        save_layout.addWidget(save_btn)
        layout.addLayout(save_layout)

        # Saved profiles list
        layout.addWidget(QLabel("Saved Profiles:"))
        self.saved_profiles_list = QListWidget()
        self.saved_profiles_list.itemClicked.connect(self._load_profile)
        self.saved_profiles_list.setMaximumHeight(100)
        layout.addWidget(self.saved_profiles_list)

        # Preview
        layout.addWidget(QLabel("Preview (active image):"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(60)
        layout.addWidget(self.preview_text)

        # Export mode section
        mode_group = QGroupBox("Export Mode")
        mode_layout = QVBoxLayout(mode_group)

        self.mode_group = QButtonGroup(self)
        self.current_location_radio = QRadioButton("Export to current image locations")
        self.new_directory_radio = QRadioButton("Export to new directory")
        self.kohya_subsets_radio = QRadioButton("Export Kohya Subsets")
        self.current_location_radio.setChecked(True)

        self.mode_group.addButton(self.current_location_radio)
        self.mode_group.addButton(self.new_directory_radio)
        self.mode_group.addButton(self.kohya_subsets_radio)

        mode_layout.addWidget(self.current_location_radio)
        mode_layout.addWidget(self.new_directory_radio)
        mode_layout.addWidget(self.kohya_subsets_radio)

        layout.addWidget(mode_group)

        # Template editor button (for Kohya mode)
        template_layout = QHBoxLayout()
        template_layout.addStretch()
        self.edit_template_btn = QPushButton("Edit TOML Template")
        self.edit_template_btn.clicked.connect(self._edit_template)
        self.edit_template_btn.setEnabled(False)
        template_layout.addWidget(self.edit_template_btn)
        layout.addLayout(template_layout)

        # Directory selection (for new directory mode)
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Output Directory:"))
        self.directory_input = QLineEdit()
        self.directory_input.setEnabled(False)
        dir_layout.addWidget(self.directory_input)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setEnabled(False)
        self.browse_btn.clicked.connect(self._browse_directory)
        dir_layout.addWidget(self.browse_btn)

        layout.addLayout(dir_layout)

        # Options section (for new directory mode)
        options_group = QGroupBox("Export Options")
        options_layout = QVBoxLayout(options_group)

        self.maintain_paths_check = QCheckBox("Maintain relative paths")
        self.maintain_paths_check.setEnabled(False)
        options_layout.addWidget(self.maintain_paths_check)

        self.copy_images_check = QCheckBox("Copy images to export directory")
        self.copy_images_check.setEnabled(False)
        options_layout.addWidget(self.copy_images_check)

        self.symlink_check = QCheckBox("Create symlinks instead of copying")
        self.symlink_check.setEnabled(False)
        options_layout.addWidget(self.symlink_check)

        layout.addWidget(options_group)

        # Connect mode change handler
        self.current_location_radio.toggled.connect(self._on_mode_changed)
        self.new_directory_radio.toggled.connect(self._on_mode_changed)
        self.kohya_subsets_radio.toggled.connect(self._on_mode_changed)

        # Connect option change handlers
        self.copy_images_check.stateChanged.connect(self._on_options_changed)
        self.symlink_check.stateChanged.connect(self._on_options_changed)

        # Export button
        export_layout = QHBoxLayout()
        export_layout.addStretch()
        self.export_btn = QPushButton("Export Selected")
        self.export_btn.clicked.connect(self._export_captions)
        export_layout.addWidget(self.export_btn)
        layout.addLayout(export_layout)

    def _on_mode_changed(self):
        """Handle export mode change"""
        new_dir_mode = self.new_directory_radio.isChecked()
        kohya_mode = self.kohya_subsets_radio.isChecked()

        # Enable/disable directory selection (required for both new_dir and kohya modes)
        self.directory_input.setEnabled(new_dir_mode or kohya_mode)
        self.browse_btn.setEnabled(new_dir_mode or kohya_mode)

        # Enable/disable options (only for new_dir mode)
        self.maintain_paths_check.setEnabled(new_dir_mode)
        self.copy_images_check.setEnabled(new_dir_mode)
        self.symlink_check.setEnabled(new_dir_mode)

        # Enable/disable template editor (only for kohya mode)
        self.edit_template_btn.setEnabled(kohya_mode)

    def _on_options_changed(self):
        """Handle option checkboxes changing"""
        # Make copy and symlink mutually exclusive
        if self.copy_images_check.isChecked():
            self.symlink_check.blockSignals(True)
            self.symlink_check.setChecked(False)
            self.symlink_check.blockSignals(False)
        elif self.symlink_check.isChecked():
            self.copy_images_check.blockSignals(True)
            self.copy_images_check.setChecked(False)
            self.copy_images_check.blockSignals(False)

    def _browse_directory(self):
        """Browse for output directory"""
        # Use persistent file dialog
        directory = self.app_manager.get_existing_directory(
            self,
            "Select Output Directory",
            'export'
        )
        if directory:
            self.directory_input.setText(str(directory))

    def _edit_template(self):
        """Open dialog to edit Kohya TOML template"""
        project = self.app_manager.get_project()

        # Get current template or use default
        current_template = project.export.get("kohya_template", self.DEFAULT_KOHYA_TEMPLATE)

        # Create dialog
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

    def _update_preview(self):
        """Update preview for active image"""
        profile_text = self.profile_input.text().strip()

        if not profile_text:
            self.preview_text.setPlainText("(No profile specified)")
            return

        current_view = self.app_manager.get_current_view()
        if current_view is None or not current_view.get_active():
            self.preview_text.setPlainText("(No active image)")
            return

        # Load image data
        img_data = self.app_manager.load_image_data(current_view.get_active())

        # Parse and apply template
        try:
            template_parts = parse_export_template(profile_text)
            caption = apply_export_template(template_parts, img_data)
            self.preview_text.setPlainText(caption if caption else "(empty)")
        except Exception as e:
            self.preview_text.setPlainText(f"Error: {e}")

    def _save_profile(self):
        """Save the current profile to the project"""
        profile_text = self.profile_input.text().strip()
        if not profile_text:
            return

        project = self.app_manager.get_project()

        # Get existing saved profiles
        if "saved_profiles" not in project.export:
            project.export["saved_profiles"] = []

        # Add profile if not already saved
        if profile_text not in project.export["saved_profiles"]:
            project.export["saved_profiles"].append(profile_text)
            self.app_manager.update_project(save=True)
            self._load_saved_profiles()

    def _load_saved_profiles(self):
        """Load saved profiles from project"""
        self.saved_profiles_list.clear()

        project = self.app_manager.get_project()
        if not project.project_file:
            return

        saved_profiles = project.export.get("saved_profiles", [])

        for profile_text in saved_profiles:
            # Create item with delete button
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(2, 2, 2, 2)

            label = QLabel(profile_text)
            item_layout.addWidget(label)

            delete_btn = QPushButton("×")
            delete_btn.setMaximumWidth(30)
            delete_btn.clicked.connect(lambda checked, p=profile_text: self._delete_profile(p))
            item_layout.addWidget(delete_btn)

            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, profile_text)
            self.saved_profiles_list.addItem(list_item)
            self.saved_profiles_list.setItemWidget(list_item, item_widget)

    def _load_profile(self, item):
        """Load a saved profile into the input"""
        profile_text = item.data(Qt.UserRole)
        if profile_text:
            self.profile_input.setText(profile_text)
            self._update_preview()

    def _delete_profile(self, profile_text: str):
        """Delete a saved profile"""
        project = self.app_manager.get_project()
        if "saved_profiles" in project.export and profile_text in project.export["saved_profiles"]:
            project.export["saved_profiles"].remove(profile_text)
            self.app_manager.update_project(save=True)
            self._load_saved_profiles()

    def _export_captions(self):
        """Export caption files for selected images"""
        # Check mode first
        new_dir_mode = self.new_directory_radio.isChecked()
        kohya_mode = self.kohya_subsets_radio.isChecked()

        # Get selected images
        working_images = self.get_selected_images()

        if not working_images:
            QMessageBox.warning(self, "No Images", "No images selected.")
            return

        # Handle Kohya export mode separately
        if kohya_mode:
            # Check for unsaved plugin changes before exporting
            if self.app_manager.has_any_plugin_unsaved_changes():
                plugins = self.app_manager.get_plugins_with_unsaved_changes()
                plugin_names = ", ".join([p.name for p in plugins])

                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    f"The following plugins have unsaved changes:\n{plugin_names}\n\n"
                    "These changes have not been applied to the project.\n"
                    "Export will use the previously saved values.\n\n"
                    "Do you want to continue with export anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply != QMessageBox.Yes:
                    return

            # Validate output directory
            output_dir = Path(self.directory_input.text().strip())
            if not output_dir or not str(output_dir):
                QMessageBox.warning(self, "No Directory", "Please select an output directory.")
                return

            # Create output directory if needed
            output_dir.mkdir(parents=True, exist_ok=True)

            # Export Kohya subsets
            try:
                exported_count = self._export_kohya_subsets(working_images, output_dir)
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Exported {exported_count} images to Kohya subsets.\nConfiguration saved to {output_dir / 'config.toml'}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Error during Kohya export: {e}")

            return

        # For caption export modes, validate profile
        profile_text = self.profile_input.text().strip()

        if not profile_text:
            QMessageBox.warning(self, "No Profile", "Please specify an export profile.")
            return

        # Validate new directory mode
        if new_dir_mode:
            output_dir = Path(self.directory_input.text().strip())
            if not output_dir or not str(output_dir):
                QMessageBox.warning(self, "No Directory", "Please select an output directory.")
                return

            # Create output directory if needed
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = None

        # Parse template
        try:
            template_parts = parse_export_template(profile_text)
        except Exception as e:
            QMessageBox.critical(self, "Template Error", f"Error parsing template: {e}")
            return

        # Export captions
        try:
            if new_dir_mode:
                exported_count = self._export_to_new_directory(
                    working_images,
                    template_parts,
                    output_dir
                )
            else:
                exported_count = self._export_to_current_location(
                    working_images,
                    template_parts
                )

            QMessageBox.information(
                self,
                "Export Complete",
                f"Exported {exported_count} caption files."
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Error during export: {e}")

    def _export_to_current_location(self, images: List[Path], template_parts) -> int:
        """Export captions to current image locations"""
        exported_count = 0

        for img_path in images:
            try:
                # Load image data
                img_data = self.app_manager.load_image_data(img_path)

                # Generate caption
                caption = apply_export_template(template_parts, img_data)

                # Write caption file (same location as image, .txt extension)
                caption_path = img_path.with_suffix('.txt')
                with open(caption_path, 'w') as f:
                    f.write(caption)

                exported_count += 1

            except Exception as e:
                print(f"Error exporting {img_path}: {e}")

        return exported_count

    def _export_to_new_directory(self, images: List[Path], template_parts, output_dir: Path) -> int:
        """Export captions to new directory with options"""
        maintain_paths = self.maintain_paths_check.isChecked()
        copy_images = self.copy_images_check.isChecked()
        create_symlinks = self.symlink_check.isChecked()

        exported_count = 0
        base_dir = self.app_manager.get_project().get_base_directory()

        for img_path in images:
            try:
                # Load image data
                img_data = self.app_manager.load_image_data(img_path)

                # Generate caption
                caption = apply_export_template(template_parts, img_data)

                # Determine output paths
                if maintain_paths and base_dir:
                    # Maintain relative path structure
                    rel_path = img_path.relative_to(base_dir)
                    caption_path = output_dir / rel_path.with_suffix('.txt')
                    img_dest_path = output_dir / rel_path
                else:
                    # Flat structure
                    caption_path = output_dir / f"{img_path.stem}.txt"
                    img_dest_path = output_dir / img_path.name

                # Create directories if needed
                caption_path.parent.mkdir(parents=True, exist_ok=True)

                # Write caption file
                with open(caption_path, 'w') as f:
                    f.write(caption)

                # Copy or symlink images if requested
                if copy_images:
                    img_dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(img_path, img_dest_path)
                elif create_symlinks:
                    img_dest_path.parent.mkdir(parents=True, exist_ok=True)
                    # Remove existing symlink if present
                    if img_dest_path.is_symlink() or img_dest_path.exists():
                        img_dest_path.unlink()
                    img_dest_path.symlink_to(img_path.resolve())

                exported_count += 1

            except Exception as e:
                print(f"Error exporting {img_path}: {e}")

        return exported_count

    def _export_kohya_subsets(self, images: List[Path], output_dir: Path) -> int:
        """Export images to Kohya subset structure with TOML config"""
        project = self.app_manager.get_project()
        image_list = project.image_list

        # Group images by repeat count
        repeat_groups = {}  # {repeat_count: [img_path1, img_path2, ...]}

        for img_path in images:
            repeat_count = image_list.get_repeat(img_path)
            if repeat_count not in repeat_groups:
                repeat_groups[repeat_count] = []
            repeat_groups[repeat_count].append(img_path)

        # Create subdirectories and copy images
        exported_count = 0
        for repeat_count, img_paths in repeat_groups.items():
            # Create subdirectory name (e.g., "images/2_repeats")
            subset_dir = output_dir / "images" / f"{repeat_count}_repeats"
            subset_dir.mkdir(parents=True, exist_ok=True)

            # Copy images to subdirectory
            for img_path in img_paths:
                try:
                    dest_path = subset_dir / img_path.name
                    shutil.copy2(img_path, dest_path)
                    exported_count += 1
                except Exception as e:
                    print(f"Error copying {img_path}: {e}")

        # Generate TOML subset entries (with 4-space indentation)
        subset_entries = []
        for repeat_count in sorted(repeat_groups.keys()):
            entry = f"""    [[datasets.subsets]]
    image_dir = "images/{repeat_count}_repeats"
    num_repeats = {repeat_count}
"""
            subset_entries.append(entry)

        # Combine all subset entries
        subsets_text = "\n".join(subset_entries)

        # Load template and replace placeholder
        template = project.export.get("kohya_template", self.DEFAULT_KOHYA_TEMPLATE)
        final_toml = template.replace("{{SUBSETS}}", subsets_text)

        # Write TOML file
        toml_path = output_dir / "config.toml"
        with open(toml_path, 'w') as f:
            f.write(final_toml)

        return exported_count
