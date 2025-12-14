"""
Caption Profile Plugin - Configure caption generation profiles
"""

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
    QCheckBox,
    QSpinBox,
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
        self.app_manager.library_changed.connect(self._load_saved_profiles)

        # Set up timer for preview updates
        from PyQt5.QtCore import QTimer

        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self._update_preview)
        self.preview_timer.start(1000)  # Update every second

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
        profile_layout = QVBoxLayout()
        profile_layout.addWidget(QLabel("Caption Profile:"))

        self.profile_input = QTextEdit()
        self.profile_input.setPlaceholderText("trigger, {class}, {camera}")
        self.profile_input.textChanged.connect(self._update_preview)
        self.profile_input.setMaximumHeight(80)
        self.profile_input.setLineWrapMode(QTextEdit.WidgetWidth)
        profile_layout.addWidget(self.profile_input)

        # Remove duplicates option
        options_layout = QHBoxLayout()
        self.remove_duplicates_checkbox = QCheckBox(
            "Remove duplicate tags from caption"
        )
        options_layout.addWidget(self.remove_duplicates_checkbox)
        self.remove_duplicates_checkbox.stateChanged.connect(self._update_preview)
        options_layout.addStretch()
        profile_layout.addLayout(options_layout)

        # Max tags limit option
        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("Max tags to include:"))
        self.max_tags_spin = QSpinBox()
        self.max_tags_spin.setRange(0, 1000)
        self.max_tags_spin.setValue(0)  # 0 = unlimited
        self.max_tags_spin.setSuffix(" (0 = unlimited)")
        self.max_tags_spin.valueChanged.connect(self._update_preview)
        limit_layout.addWidget(self.max_tags_spin)
        limit_layout.addStretch()
        profile_layout.addLayout(limit_layout)

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
        self.preview_text.setMaximumHeight(100)
        self.preview_text.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(self.preview_text)

        # Note: Active profiles are automatically applied when tags change
        # No manual apply button needed - captions update in real-time

    def _update_preview(self):
        """Update preview for active image"""
        profile_text = self.profile_input.toPlainText().strip()

        if not profile_text:
            self.preview_text.setPlainText("(No profile specified)")
            return

        current_view = self.app_manager.get_current_view()
        if current_view is None:
            self.preview_text.setPlainText("(No current view)")
            return

        active_image = current_view.get_active()
        if not active_image:
            self.preview_text.setPlainText("(No active image)")
            return

        # Load image data
        try:
            img_data = self.app_manager.load_image_data(active_image)

            # Parse and apply template
            template_parts = parse_export_template(profile_text)
            remove_duplicates = self.remove_duplicates_checkbox.isChecked()
            max_tags = (
                self.max_tags_spin.value() if self.max_tags_spin.value() > 0 else None
            )
            caption = apply_export_template(
                template_parts,
                img_data,
                remove_duplicates=remove_duplicates,
                max_tags=max_tags,
            )
            self.preview_text.setPlainText(caption if caption else "(empty)")
        except Exception as e:
            self.preview_text.setPlainText(f"Error: {e}")

    def _save_profile(self):
        """Save the current profile to the project"""
        profile_text = self.profile_input.toPlainText().strip()
        if not profile_text:
            QMessageBox.warning(
                self, "Empty Profile", "Please enter a profile text before saving."
            )
            return

        # Save to appropriate location based on current view
        if (
            self.app_manager.current_view_mode == "library"
            and self.app_manager.current_library
        ):
            # Library view - save to library metadata
            if not hasattr(self.app_manager.current_library, "caption_profiles"):
                self.app_manager.current_library.caption_profiles = []

            if profile_text not in self.app_manager.current_library.caption_profiles:
                self.app_manager.current_library.caption_profiles.append(profile_text)

                # Save library to persist profiles
                try:
                    self.app_manager.current_library.save()
                    self._load_saved_profiles()
                    QMessageBox.information(
                        self,
                        "Profile Saved",
                        f"Profile '{profile_text[:50]}...' has been saved to library.",
                    )
                except Exception as e:
                    QMessageBox.critical(
                        self, "Save Error", f"Failed to save profile to library: {e}"
                    )
            else:
                QMessageBox.information(
                    self,
                    "Already Saved",
                    "This profile is already saved in the library.",
                )
        else:
            # Project view - save to project
            project = self.app_manager.get_project()
            if not project or not project.project_file:
                QMessageBox.warning(
                    self,
                    "No Project",
                    "Please load a project first before saving profiles.",
                )
                return

            # Get existing saved profiles
            if "caption_profiles" not in project.export:
                project.export["caption_profiles"] = []

            # Add profile if not already saved
            if profile_text not in project.export["caption_profiles"]:
                project.export["caption_profiles"].append(profile_text)

                # Save the project immediately
                try:
                    project.save()
                    self._load_saved_profiles()
                    QMessageBox.information(
                        self,
                        "Profile Saved",
                        f"Profile '{profile_text[:50]}...' has been saved to project.",
                    )
                except Exception as e:
                    QMessageBox.critical(
                        self, "Save Error", f"Failed to save profile to project: {e}"
                    )
            else:
                QMessageBox.information(
                    self,
                    "Already Saved",
                    "This profile is already saved in the project.",
                )

    def _set_active_profile(self):
        """Set the current profile as the active profile"""
        profile_text = self.profile_input.toPlainText().strip()
        if not profile_text:
            QMessageBox.warning(
                self, "No Profile", "Please specify a caption profile first."
            )
            return

        # Save to appropriate location based on current view
        if (
            self.app_manager.current_view_mode == "library"
            and self.app_manager.current_library
        ):
            # Library view - store on library object
            self.app_manager.current_library.active_caption_profile = profile_text
            self.app_manager.current_library.caption_profile_remove_duplicates = (
                self.remove_duplicates_checkbox.isChecked()
            )
            self.app_manager.current_library.caption_profile_max_tags = (
                self.max_tags_spin.value()
            )

            # Save library to persist the active profile
            try:
                self.app_manager.current_library.save()
            except Exception as e:
                print(f"Warning: Could not save library with active profile: {e}")
        else:
            # Project view - store in project export settings
            project = self.app_manager.get_project()
            if project:
                project.export["active_caption_profile"] = profile_text
                project.export["caption_profile_remove_duplicates"] = (
                    self.remove_duplicates_checkbox.isChecked()
                )
                project.export["caption_profile_max_tags"] = self.max_tags_spin.value()
                try:
                    project.save()
                except Exception as e:
                    print(f"Warning: Could not save project with active profile: {e}")

        # Update the label
        self.active_profile_label.setText(f"Active Profile: {profile_text}")
        self._load_saved_profiles()  # Refresh the list to show active indicator

        # Apply captions to all existing images in current view
        self._apply_captions_to_all_images(profile_text)

        QMessageBox.information(
            self,
            "Profile Activated",
            f"Caption profile '{profile_text[:50]}...' has been set as active.\n\n"
            "Captions have been applied to all existing images and will be updated automatically when tags change.",
        )

    def _load_saved_profiles(self):
        """Load saved profiles from current view (library or project)"""
        self.saved_profiles_list.clear()

        active_profile = ""
        saved_profiles = []

        # Load based on current view
        if (
            self.app_manager.current_view_mode == "library"
            and self.app_manager.current_library
        ):
            # Library view - check library metadata for saved profiles
            active_profile = getattr(
                self.app_manager.current_library, "active_caption_profile", ""
            )
            saved_profiles = getattr(
                self.app_manager.current_library, "caption_profiles", []
            )
        else:
            # Project view
            project = self.app_manager.get_project()
            if project and hasattr(project, "project_file") and project.project_file:
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
            delete_btn.clicked.connect(
                lambda checked, p=profile_text: self._delete_profile(p)
            )
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
        # Check if this is the active profile
        active_profile = ""
        if (
            self.app_manager.current_view_mode == "library"
            and self.app_manager.current_library
        ):
            active_profile = getattr(
                self.app_manager.current_library, "active_caption_profile", ""
            )
            if active_profile == profile_text:
                QMessageBox.warning(
                    self,
                    "Cannot Delete",
                    "Cannot delete the active caption profile.\n"
                    "Please set a different profile as active first.",
                )
                return

            # Delete from library
            if (
                hasattr(self.app_manager.current_library, "caption_profiles")
                and profile_text in self.app_manager.current_library.caption_profiles
            ):
                self.app_manager.current_library.caption_profiles.remove(profile_text)
                try:
                    self.app_manager.current_library.save()
                    self._load_saved_profiles()
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Delete Error",
                        f"Failed to delete profile from library: {e}",
                    )
        else:
            # Project view
            project = self.app_manager.get_project()
            if project.export.get("active_caption_profile") == profile_text:
                QMessageBox.warning(
                    self,
                    "Cannot Delete",
                    "Cannot delete the active caption profile.\n"
                    "Please set a different profile as active first.",
                )
                return

            if (
                "caption_profiles" in project.export
                and profile_text in project.export["caption_profiles"]
            ):
                project.export["caption_profiles"].remove(profile_text)
                try:
                    project.save()
                    self._load_saved_profiles()
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Delete Error",
                        f"Failed to delete profile from project: {e}",
                    )

    def _apply_captions_to_all_images(self, profile_text: str):
        """Apply caption profile to all images in current view"""
        try:
            from ..utils import parse_export_template, apply_export_template

            # Parse template
            template_parts = parse_export_template(profile_text)
            remove_duplicates = self.remove_duplicates_checkbox.isChecked()
            max_tags = (
                self.max_tags_spin.value() if self.max_tags_spin.value() > 0 else None
            )

            # Get all images from current view
            current_view = self.app_manager.get_current_view()
            if not current_view:
                return

            all_images = current_view.get_all_paths()
            if not all_images:
                return

            # Apply captions to all images
            success_count = 0
            error_count = 0

            for img_path in all_images:
                try:
                    # Load image data
                    img_data = self.app_manager.load_image_data(img_path)

                    # Generate caption
                    caption = apply_export_template(
                        template_parts,
                        img_data,
                        remove_duplicates=remove_duplicates,
                        max_tags=max_tags,
                    )

                    # Update image data caption
                    img_data.caption = caption if caption else ""

                    # Save image data immediately
                    if (
                        self.app_manager.current_view_mode == "project"
                        and self.app_manager.current_project
                    ):
                        json_path = (
                            self.app_manager.current_project.get_image_json_path(
                                img_path
                            )
                        )
                    else:
                        # For library view, construct path manually
                        json_path = img_path.with_suffix(".json")

                    img_data.save(json_path)
                    success_count += 1

                except Exception as e:
                    error_count += 1
                    print(f"Error applying caption to {img_path.name}: {e}")

            print(
                f"Caption profile applied: {success_count} success, {error_count} errors"
            )

            # Refresh any open gallery windows to show updated captions
            try:
                # Find and refresh any gallery widgets
                from PyQt5.QtWidgets import QApplication

                for widget in QApplication.allWidgets():
                    if widget.__class__.__name__ == "Gallery":
                        widget.refresh()
            except Exception as e:
                print(f"Error refreshing gallery: {e}")

        except Exception as e:
            print(f"Error in _apply_captions_to_all_images: {e}")
