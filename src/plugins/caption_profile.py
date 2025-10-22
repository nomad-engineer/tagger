"""
Caption Profile Plugin - Configure caption generation profiles
"""
from typing import List
from pathlib import Path
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QTextEdit, QMessageBox, QWidget
)
from PyQt5.QtCore import Qt

from ..plugin_base import PluginWindow
from ..utils import parse_export_template, apply_export_template


class CaptionProfilePlugin(PluginWindow):
    """Plugin to configure caption generation profiles"""

    def __init__(self, app_manager, parent=None):
        super().__init__(app_manager, parent)

        self.name = "Caption Profile"
        self.description = "Configure caption generation profiles"
        self.shortcut = "Ctrl+P"

        self.setWindowTitle(self.name)
        self.resize(700, 500)

        self._setup_ui()

        # Connect to signals
        self.app_manager.project_changed.connect(self._load_saved_profiles)
        self.app_manager.project_changed.connect(self._update_preview)
        self.app_manager.library_changed.connect(self._load_saved_profiles)
        self.app_manager.library_changed.connect(self._update_preview)

        # Initial load
        self._load_saved_profiles()
        self._update_preview()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Instructions
        instructions = QLabel(
            "Caption profile format: trigger, {class}, {camera}, {details}[0:3]\n"
            "{category} = all tags from category, {category}[0:3] = first 3 tags\n\n"
            "The caption is written to each image's JSON file and updated whenever tags change."
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(instructions)

        # Profile string entry
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Caption Profile:"))

        self.profile_input = QLineEdit()
        self.profile_input.setPlaceholderText("trigger, {class}, {camera}")
        self.profile_input.textChanged.connect(self._update_preview)
        profile_layout.addWidget(self.profile_input)

        layout.addLayout(profile_layout)

        # Buttons for save and set active
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        save_btn = QPushButton("Save Profile")
        save_btn.clicked.connect(self._save_profile)
        button_layout.addWidget(save_btn)

        set_active_btn = QPushButton("Set as Active Profile")
        set_active_btn.clicked.connect(self._set_active_profile)
        button_layout.addWidget(set_active_btn)

        layout.addLayout(button_layout)

        # Saved profiles list
        layout.addWidget(QLabel("Saved Profiles:"))
        self.saved_profiles_list = QListWidget()
        self.saved_profiles_list.itemClicked.connect(self._load_profile)
        self.saved_profiles_list.setMaximumHeight(150)
        layout.addWidget(self.saved_profiles_list)

        # Active profile indicator
        self.active_profile_label = QLabel()
        self.active_profile_label.setStyleSheet("color: green; font-weight: bold;")
        layout.addWidget(self.active_profile_label)

        # Preview
        layout.addWidget(QLabel("Preview (active image):"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(60)
        layout.addWidget(self.preview_text)

        # Apply captions button
        apply_layout = QHBoxLayout()
        apply_layout.addStretch()
        apply_btn = QPushButton("Apply Caption to All Images")
        apply_btn.clicked.connect(self._apply_captions)
        apply_layout.addWidget(apply_btn)
        layout.addLayout(apply_layout)

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
        if "caption_profiles" not in project.export:
            project.export["caption_profiles"] = []

        # Add profile if not already saved
        if profile_text not in project.export["caption_profiles"]:
            project.export["caption_profiles"].append(profile_text)
            self.app_manager.update_project(save=True)
            self._load_saved_profiles()

    def _set_active_profile(self):
        """Set the current profile as the active profile"""
        profile_text = self.profile_input.text().strip()
        if not profile_text:
            QMessageBox.warning(self, "No Profile", "Please specify a caption profile first.")
            return

        # Save to appropriate location based on current view
        if self.app_manager.current_view_mode == "library" and self.app_manager.current_library:
            # Library view - store on library object
            self.app_manager.current_library.active_caption_profile = profile_text
        else:
            # Project view - store in project export settings
            project = self.app_manager.get_project()
            project.export["active_caption_profile"] = profile_text
            self.app_manager.update_project(save=True)

        # Update the label
        self.active_profile_label.setText(f"Active Profile: {profile_text}")

        QMessageBox.information(
            self,
            "Profile Activated",
            "Caption profile has been set as active.\n\n"
            "Captions will be automatically updated when tags change."
        )

    def _load_saved_profiles(self):
        """Load saved profiles from current view (library or project)"""
        self.saved_profiles_list.clear()

        active_profile = ""
        saved_profiles = []

        # Load based on current view
        if self.app_manager.current_view_mode == "library" and self.app_manager.current_library:
            # Library view
            active_profile = getattr(self.app_manager.current_library, 'active_caption_profile', "")
            # Library doesn't have saved profiles yet, just active profile
        else:
            # Project view
            project = self.app_manager.get_project()
            if project and hasattr(project, 'project_file') and project.project_file:
                active_profile = project.export.get("active_caption_profile", "")
                saved_profiles = project.export.get("caption_profiles", [])

        # Update active profile label
        if active_profile:
            self.active_profile_label.setText(f"Active Profile: {active_profile}")
        else:
            self.active_profile_label.setText("Active Profile: None")

        for profile_text in saved_profiles:
            # Create item with delete button
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(2, 2, 2, 2)

            # Show indicator if this is the active profile
            if profile_text == active_profile:
                label_text = f"★ {profile_text}"
            else:
                label_text = profile_text

            label = QLabel(label_text)
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

        # Check if this is the active profile
        if project.export.get("active_caption_profile") == profile_text:
            QMessageBox.warning(
                self,
                "Cannot Delete",
                "Cannot delete the active caption profile.\n"
                "Please set a different profile as active first."
            )
            return

        if "caption_profiles" in project.export and profile_text in project.export["caption_profiles"]:
            project.export["caption_profiles"].remove(profile_text)
            self.app_manager.update_project(save=True)
            self._load_saved_profiles()

    def _apply_captions(self):
        """Apply caption profile to all images in project"""
        profile_text = self.profile_input.text().strip()

        if not profile_text:
            QMessageBox.warning(self, "No Profile", "Please specify a caption profile.")
            return

        # Get working images (selected or all)
        working_images = self.get_selected_images()

        if not working_images:
            QMessageBox.warning(self, "No Images", "No images to apply captions to.")
            return

        # Parse template
        try:
            template_parts = parse_export_template(profile_text)
        except Exception as e:
            QMessageBox.critical(self, "Template Error", f"Error parsing template: {e}")
            return

        # Apply captions
        try:
            count = 0
            for img_path in working_images:
                # Load image data
                img_data = self.app_manager.load_image_data(img_path)

                # Generate caption
                caption = apply_export_template(template_parts, img_data)

                # Update image data caption
                img_data.caption = caption

                # Save image data
                json_path = self.app_manager.get_project().get_image_json_path(img_path)
                img_data.save(json_path)

                count += 1

            QMessageBox.information(
                self,
                "Captions Applied",
                f"Applied caption profile to {count} image(s)."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error applying captions: {e}")
