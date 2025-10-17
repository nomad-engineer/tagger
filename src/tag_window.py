"""
Tag Window - View and edit tags for selected images with fuzzy search
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QEvent
from pathlib import Path
from typing import List

from .utils import fuzzy_search
from .data_models import ImageData, Tag


class TagWindow(QWidget):
    """Tag editor window for viewing and modifying tags"""

    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self.all_tags = []
        self._updating = False

        self.setWindowTitle("Tag Editor")
        self.setMinimumSize(300, 200)
        self.resize(400, 500)  # Default size, but can be resized smaller

        self._setup_ui()

        # Connect to signals
        self.app_manager.selection_changed.connect(self._load_tags)
        self.app_manager.project_changed.connect(self._update_tag_suggestions)

        # Initial load
        self._update_tag_suggestions()
        self._load_tags()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)

        # Info label
        self.info_label = QLabel("No images selected")
        layout.addWidget(self.info_label)

        # Entry field for new tag
        entry_layout = QHBoxLayout()
        entry_layout.addWidget(QLabel("New tag:"))
        self.tag_entry = QLineEdit()
        self.tag_entry.setPlaceholderText("category:value")
        self.tag_entry.returnPressed.connect(self._add_tag)
        self.tag_entry.textChanged.connect(self._on_entry_changed)
        self.tag_entry.installEventFilter(self)  # Install event filter for custom key handling
        entry_layout.addWidget(self.tag_entry)
        layout.addLayout(entry_layout)

        # Inline suggestion list (replaces QCompleter popup)
        self.suggestion_list = QListWidget()
        self.suggestion_list.setMaximumHeight(150)
        self.suggestion_list.setVisible(False)
        self.suggestion_list.itemClicked.connect(self._accept_suggestion)
        # Use system theme colors - only add border
        self.suggestion_list.setStyleSheet("QListWidget { border: 1px solid palette(mid); }")
        layout.addWidget(self.suggestion_list)

        # Tags list
        layout.addWidget(QLabel("Tags:"))
        self.tags_list = QListWidget()
        self.tags_list.itemDoubleClicked.connect(self._edit_tag)
        self.tags_list.installEventFilter(self)  # Install event filter for Del key
        layout.addWidget(self.tags_list)

        # Instructions
        instructions = QLabel(
            "• Enter: add tag\n"
            "• Tab/↓: browse suggestions\n"
            "• Double-click: edit tag\n"
            "• Del: delete tag"
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(instructions)

    def _update_tag_suggestions(self):
        """Update autocomplete suggestions with all tags in project"""
        self.all_tags = self.app_manager.get_all_tags_in_project()

    def _on_entry_changed(self, text: str):
        """Handle entry text change for fuzzy search - updates inline suggestion list"""
        if not text or self._updating:
            self.suggestion_list.clear()
            self.suggestion_list.setVisible(False)
            return

        # Perform fuzzy search on tags
        if self.all_tags:
            matches = fuzzy_search(text, self.all_tags, threshold=0.1)

            if matches:
                # Show top 10 matches in suggestion list
                self.suggestion_list.clear()
                for match_text, score in matches[:10]:
                    self.suggestion_list.addItem(match_text)

                # Select first item by default
                if self.suggestion_list.count() > 0:
                    self.suggestion_list.setCurrentRow(0)

                self.suggestion_list.setVisible(True)
            else:
                self.suggestion_list.clear()
                self.suggestion_list.setVisible(False)
        else:
            self.suggestion_list.clear()
            self.suggestion_list.setVisible(False)

    def _load_tags(self):
        """Load tags from selected/active images"""
        self._updating = True

        selection = self.app_manager.get_selection()
        working_images = selection.get_working_images()

        self.tags_list.clear()

        if not working_images:
            self.info_label.setText("No images selected")
            self._updating = False
            return

        # Get all unique tags from working images
        all_tags = []
        for img_path in working_images:
            img_data = self.app_manager.load_image_data(img_path)
            for tag in img_data.tags:
                tag_str = str(tag)
                if tag_str not in [str(t) for t in all_tags]:
                    all_tags.append(tag)

        # Update info
        if len(working_images) == 1:
            img_name = self.app_manager.load_image_data(working_images[0]).name
            self.info_label.setText(f"Editing: {img_name}")
        else:
            self.info_label.setText(f"Editing: {len(working_images)} images")

        # Populate list
        for tag in all_tags:
            item = QListWidgetItem(str(tag))
            item.setData(Qt.UserRole, tag)
            self.tags_list.addItem(item)

        self._updating = False

    def _add_tag(self):
        """Add new tag to selected images"""
        tag_text = self.tag_entry.text().strip()
        if not tag_text:
            return

        # Parse tag (category:value)
        parts = tag_text.split(':', 1)
        if len(parts) != 2:
            return

        category = parts[0].strip()
        value = parts[1].strip()

        if not category or not value:
            return

        # Add tag to all working images
        selection = self.app_manager.get_selection()
        working_images = selection.get_working_images()

        for img_path in working_images:
            img_data = self.app_manager.load_image_data(img_path)
            img_data.add_tag(category, value)
            self.app_manager.save_image_data(img_path, img_data)

        # Clear entry and reload
        self.tag_entry.clear()
        self._load_tags()
        self._update_tag_suggestions()
        self.app_manager.update_project(save=True)

    def _edit_tag(self, item: QListWidgetItem):
        """Edit an existing tag"""
        if not item:
            return

        old_tag = item.data(Qt.UserRole)
        if not old_tag:
            return

        # Disconnect any existing itemChanged connections to prevent multiple handlers
        try:
            self.tags_list.itemChanged.disconnect()
        except:
            pass

        # Enable editing of the item
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.tags_list.editItem(item)

        # Connect to item changed signal with the old tag stored
        self.tags_list.itemChanged.connect(lambda it: self._on_tag_edited(it, old_tag))

    def _on_tag_edited(self, item: QListWidgetItem, old_tag: Tag):
        """Handle tag edit completion"""
        try:
            self.tags_list.itemChanged.disconnect()
        except:
            pass

        if not item:
            return

        new_text = item.text().strip()
        selection = self.app_manager.get_selection()
        working_images = selection.get_working_images()

        if not new_text:
            # Delete tag from all images
            for img_path in working_images:
                img_data = self.app_manager.load_image_data(img_path)
                if old_tag in img_data.tags:
                    img_data.remove_tag(old_tag)
                    self.app_manager.save_image_data(img_path, img_data)
        else:
            # Parse new tag
            parts = new_text.split(':', 1)
            if len(parts) == 2:
                new_category = parts[0].strip()
                new_value = parts[1].strip()

                if new_category and new_value:
                    # Update tag in all images
                    for img_path in working_images:
                        img_data = self.app_manager.load_image_data(img_path)
                        # Remove old tag
                        if old_tag in img_data.tags:
                            idx = img_data.tags.index(old_tag)
                            img_data.tags[idx] = Tag(new_category, new_value)
                            self.app_manager.save_image_data(img_path, img_data)

        # Reload tags
        self._load_tags()
        self._update_tag_suggestions()
        self.app_manager.update_project(save=True)

    def _delete_tag(self, item: QListWidgetItem):
        """Delete a tag from all working images"""
        if not item:
            return

        tag_to_delete = item.data(Qt.UserRole)
        if not tag_to_delete:
            return

        selection = self.app_manager.get_selection()
        working_images = selection.get_working_images()

        # Delete tag from all images
        for img_path in working_images:
            img_data = self.app_manager.load_image_data(img_path)
            if tag_to_delete in img_data.tags:
                img_data.remove_tag(tag_to_delete)
                self.app_manager.save_image_data(img_path, img_data)

        # Reload tags
        self._load_tags()
        self._update_tag_suggestions()
        self.app_manager.update_project(save=True)

    def eventFilter(self, obj, event):
        """Handle keyboard events for inline suggestion navigation and tag deletion"""
        # Check if widgets exist (may be called during initialization)
        if not hasattr(self, 'tags_list') or not hasattr(self, 'tag_entry'):
            return super().eventFilter(obj, event)

        if obj == self.tag_entry and event.type() == QEvent.KeyPress:
            if self.suggestion_list.isVisible() and self.suggestion_list.count() > 0:
                key = event.key()

                if key == Qt.Key_Down:
                    # Move selection down in suggestion list
                    current_row = self.suggestion_list.currentRow()
                    if current_row < self.suggestion_list.count() - 1:
                        self.suggestion_list.setCurrentRow(current_row + 1)
                    return True  # Event handled

                elif key == Qt.Key_Up:
                    # Move selection up in suggestion list
                    current_row = self.suggestion_list.currentRow()
                    if current_row > 0:
                        self.suggestion_list.setCurrentRow(current_row - 1)
                    return True  # Event handled

                elif key == Qt.Key_Tab:
                    # Tab always accepts suggestion
                    current_item = self.suggestion_list.currentItem()
                    if current_item:
                        self._accept_suggestion(current_item)
                        return True

                elif key == Qt.Key_Escape:
                    # Hide suggestions
                    self.suggestion_list.setVisible(False)
                    return True
            else:
                # No suggestions visible - handle up/down for image navigation
                if not self.tag_entry.text():
                    if event.key() == Qt.Key_Up:
                        self._change_active_image(-1)
                        return True
                    elif event.key() == Qt.Key_Down:
                        self._change_active_image(1)
                        return True

        elif obj == self.tags_list and event.type() == QEvent.KeyPress:
            # Handle Del key on tags list
            if event.key() == Qt.Key_Delete:
                current_item = self.tags_list.currentItem()
                if current_item:
                    self._delete_tag(current_item)
                    return True

        return super().eventFilter(obj, event)

    def _accept_suggestion(self, item):
        """Accept the selected suggestion and insert into tag entry"""
        if not item:
            return

        suggestion = item.text()
        self.tag_entry.setText(suggestion)
        self.tag_entry.setFocus()

        # Hide suggestions after acceptance
        self.suggestion_list.clear()
        self.suggestion_list.setVisible(False)

    def keyPressEvent(self, event):
        """Handle keyboard events at window level"""
        super().keyPressEvent(event)

    def _change_active_image(self, direction: int):
        """Change the active image in the gallery"""
        selection = self.app_manager.get_selection()
        filtered_images = selection.filtered_images

        if not filtered_images or not selection.active_image:
            return

        try:
            current_idx = filtered_images.index(selection.active_image)
            new_idx = current_idx + direction

            if 0 <= new_idx < len(filtered_images):
                selection.set_active(filtered_images[new_idx])
                self.app_manager.update_selection()
        except ValueError:
            pass

    def showEvent(self, event):
        """Update when window is shown"""
        super().showEvent(event)
        self._update_tag_suggestions()
        self._load_tags()
