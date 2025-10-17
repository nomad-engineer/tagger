"""
Export Window - Configure and export caption files
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QTextEdit, QMessageBox
)
from PyQt5.QtCore import Qt
from pathlib import Path

from .utils import parse_export_template, apply_export_template
from .data_models import ImageData


class Export(QWidget):
    """Export window for creating caption files"""

    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager

        self.setWindowTitle("Export")
        self.setMinimumSize(300, 200)
        self.resize(600, 500)  # Default size, but can be resized smaller

        self._setup_ui()

        # Connect to signals
        self.app_manager.project_changed.connect(self._load_saved_profiles)
        self.app_manager.selection_changed.connect(self._update_preview)

        # Initial load
        self._load_saved_profiles()
        self._update_preview()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel(
            "Export profile format: trigger, {class}, {camera}, {details}[0:3]\n"
            "{category} = all tags from category, {category}[0:3] = first 3 tags"
        )
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
        layout.addWidget(self.saved_profiles_list)

        # Preview
        layout.addWidget(QLabel("Preview (active image):"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(80)
        layout.addWidget(self.preview_text)

        # Export button
        export_layout = QHBoxLayout()
        export_layout.addStretch()
        self.export_btn = QPushButton("Export Selected")
        self.export_btn.clicked.connect(self._export_captions)
        export_layout.addWidget(self.export_btn)
        layout.addLayout(export_layout)

    def _update_preview(self):
        """Update preview for active image"""
        profile_text = self.profile_input.text().strip()

        if not profile_text:
            self.preview_text.setPlainText("(No profile specified)")
            return

        selection = self.app_manager.get_selection()
        if not selection.active_image:
            self.preview_text.setPlainText("(No active image)")
            return

        # Load image data
        img_data = self.app_manager.load_image_data(selection.active_image)

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
        profile_text = self.profile_input.text().strip()

        if not profile_text:
            QMessageBox.warning(self, "No Profile", "Please specify an export profile.")
            return

        selection = self.app_manager.get_selection()
        working_images = selection.get_working_images()

        if not working_images:
            QMessageBox.warning(self, "No Images", "No images selected.")
            return

        # Parse template
        try:
            template_parts = parse_export_template(profile_text)
        except Exception as e:
            QMessageBox.critical(self, "Template Error", f"Error parsing template: {e}")
            return

        # Export captions
        exported_count = 0
        for img_path in working_images:
            try:
                # Load image data
                img_data = self.app_manager.load_image_data(img_path)

                # Generate caption
                caption = apply_export_template(template_parts, img_data)

                # Write caption file (same name as image, .txt extension)
                caption_path = img_path.with_suffix('.txt')
                with open(caption_path, 'w') as f:
                    f.write(caption)

                exported_count += 1

            except Exception as e:
                print(f"Error exporting {img_path}: {e}")

        QMessageBox.information(
            self,
            "Export Complete",
            f"Exported {exported_count} caption files."
        )
