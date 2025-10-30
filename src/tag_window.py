"""
Tag Window - View and edit tags for selected images with fuzzy search
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView
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

        # Create scroll area for content
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Create container widget for scroll area
        self.scroll_content = QWidget()
        self.scroll_area.setWidget(self.scroll_content)

        # Main layout for the window
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.scroll_area)

        self._setup_ui()

        # Connect to signals
        self.app_manager.project_changed.connect(self._load_tags)
        self.app_manager.project_changed.connect(self._update_tag_suggestions)
        self.app_manager.project_changed.connect(self._update_window_title)
        self.app_manager.library_changed.connect(self._load_tags)
        self.app_manager.library_changed.connect(self._update_tag_suggestions)
        self.app_manager.library_changed.connect(self._update_window_title)

        # Initial load
        self._update_tag_suggestions()
        self._load_tags()
        self._update_window_title()

    def _update_window_title(self):
        """Update window title to show library/project name"""
        library = self.app_manager.get_library()
        project = self.app_manager.get_project()

        # Build title
        title_parts = ["Tag Editor"]

        # Add view name
        if self.app_manager.current_view_mode == "project" and project and project.project_name:
            title_parts.append(project.project_name)
        elif library and library.library_name:
            title_parts.append(library.library_name)

        self.setWindowTitle(" - ".join(title_parts))

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

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

        # Tags table (two columns: Tag and Count)
        layout.addWidget(QLabel("Tags:"))

        # Search box for filtering table
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.tag_search_input = QLineEdit()
        self.tag_search_input.setPlaceholderText("Filter tags...")
        self.tag_search_input.textChanged.connect(self._filter_table)
        search_layout.addWidget(self.tag_search_input)
        layout.addLayout(search_layout)

        self.tags_table = QTableWidget()
        self.tags_table.setColumnCount(2)
        self.tags_table.setHorizontalHeaderLabels(["Tag", "Count"])

        # Make Tag column editable, Count column read-only
        # Resize columns appropriately
        header = self.tags_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Tag column stretches
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Count column fits content

        # Connect signals
        self.tags_table.itemDoubleClicked.connect(self._edit_tag)
        self.tags_table.installEventFilter(self)  # Install event filter for Del key
        layout.addWidget(self.tags_table)

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
        # Get only full tags (not categories) for suggestions
        self.all_tags = self.app_manager.get_tag_list().get_all_full_tags()

    def _on_entry_changed(self, text: str):
        """Handle entry text change for fuzzy search - updates inline suggestion list"""
        if not text or self._updating:
            self.suggestion_list.clear()
            self.suggestion_list.setVisible(False)
            return

        # Perform fuzzy search on tags
        if self.all_tags:
            matches = fuzzy_search(text, self.all_tags)

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

    def _filter_table(self, text: str):
        """Filter tags table based on fuzzy search"""
        if not text:
            # Show all rows
            for row in range(self.tags_table.rowCount()):
                self.tags_table.setRowHidden(row, False)
            return

        # Collect all tag strings from table
        all_tags = []
        for row in range(self.tags_table.rowCount()):
            tag_item = self.tags_table.item(row, 0)
            if tag_item:
                all_tags.append((row, tag_item.text()))

        # Perform fuzzy search
        tag_strings = [tag for _, tag in all_tags]
        matches = fuzzy_search(text, tag_strings)

        # Create set of matching tag strings
        matching_tags = {match_text for match_text, score in matches}

        # Show/hide rows based on matches
        for row, tag_text in all_tags:
            self.tags_table.setRowHidden(row, tag_text not in matching_tags)

    def _load_tags(self):
        """Load tags from selected/active images"""
        self._updating = True

        current_view = self.app_manager.get_current_view()
        working_images = current_view.get_working_images() if current_view else []

        self.tags_table.setRowCount(0)

        if not working_images:
            # No images selected - show project-wide tag counts
            self.info_label.setText("No images selected - showing all project tags")
            self._load_project_tags()
            self._updating = False
            return

        # Update info
        if len(working_images) == 1:
            img_name = self.app_manager.load_image_data(working_images[0]).name
            self.info_label.setText(f"Editing: {img_name}")
        else:
            self.info_label.setText(f"Editing: {len(working_images)} images")

        # Track tag occurrences
        tag_occurrences = {}  # tag_str -> list of (tag_object, img_path)

        for img_path in working_images:
            img_data = self.app_manager.load_image_data(img_path)
            for tag in img_data.tags:
                tag_str = str(tag)
                if tag_str not in tag_occurrences:
                    tag_occurrences[tag_str] = []
                tag_occurrences[tag_str].append((tag, img_path))

        # Populate table based on number of images
        if len(working_images) == 1:
            # Single image: show ALL tags including duplicates
            img_data = self.app_manager.load_image_data(working_images[0])
            for idx, tag in enumerate(img_data.tags):
                tag_str = str(tag)
                # Count duplicates in this single image
                dup_count = sum(1 for t in img_data.tags if str(t) == tag_str)

                # Build count text
                if dup_count > 1:
                    num_dups = dup_count - 1
                    dup_word = "duplicate" if num_dups == 1 else "duplicates"
                    count_text = f"{dup_count}, {num_dups} {dup_word}"
                else:
                    count_text = ""

                # Add row to table
                self._add_tag_row(tag_str, count_text, tag, idx)
        else:
            # Multiple images: show unique tags with counts
            for tag_str, occurrences in sorted(tag_occurrences.items()):
                tag = occurrences[0][0]  # Use first occurrence as representative
                count = len(occurrences)

                # Count total occurrences across all selected images (including duplicates within images)
                total_count = 0
                for _, img_path in occurrences:
                    img_data = self.app_manager.load_image_data(img_path)
                    total_count += sum(1 for t in img_data.tags if str(t) == tag_str)

                # Build count text
                if total_count > count:
                    num_dups = total_count - count
                    dup_word = "duplicate" if num_dups == 1 else "duplicates"
                    count_text = f"{total_count}, {num_dups} {dup_word}"
                else:
                    count_text = str(count)

                # Add row to table
                self._add_tag_row(tag_str, count_text, tag, count)

        # Clear search box to show all rows
        self.tag_search_input.clear()

        self._updating = False

    def _add_tag_row(self, tag_str: str, count_text: str, tag_obj, user_data):
        """Add a row to the tags table"""
        row = self.tags_table.rowCount()
        self.tags_table.insertRow(row)

        # Tag column (editable)
        tag_item = QTableWidgetItem(tag_str)
        tag_item.setData(Qt.UserRole, tag_obj)
        tag_item.setData(Qt.UserRole + 1, user_data)
        self.tags_table.setItem(row, 0, tag_item)

        # Count column (read-only)
        count_item = QTableWidgetItem(count_text)
        count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)  # Make read-only
        self.tags_table.setItem(row, 1, count_item)

    def _load_project_tags(self):
        """Load all tags from the entire project with counts"""
        # Get all images in project
        image_list = self.app_manager.get_image_list()
        if not image_list:
            return

        all_images = image_list.get_all_paths()
        if not all_images:
            return

        # Track tag occurrences across project
        tag_occurrences = {}  # tag_str -> list of (tag_object, img_path)

        for img_path in all_images:
            img_data = self.app_manager.load_image_data(img_path)
            for tag in img_data.tags:
                tag_str = str(tag)
                if tag_str not in tag_occurrences:
                    tag_occurrences[tag_str] = []
                tag_occurrences[tag_str].append((tag, img_path))

        # Populate table with project-wide counts
        for tag_str, occurrences in sorted(tag_occurrences.items()):
            tag = occurrences[0][0]  # Use first occurrence as representative
            count = len(occurrences)

            # Count total occurrences across all images (including duplicates)
            total_count = 0
            for _, img_path in occurrences:
                img_data = self.app_manager.load_image_data(img_path)
                total_count += sum(1 for t in img_data.tags if str(t) == tag_str)

            # Build count text
            if total_count > count:
                num_dups = total_count - count
                dup_word = "duplicate" if num_dups == 1 else "duplicates"
                count_text = f"{total_count}, {num_dups} {dup_word}"
            else:
                count_text = str(count)

            # Add row to table
            self._add_tag_row(tag_str, count_text, tag, count)

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

        # Add tag to all working images (only if not already present)
        current_view = self.app_manager.get_current_view()
        working_images = current_view.get_working_images() if current_view else []

        for img_path in working_images:
            img_data = self.app_manager.load_image_data(img_path)

            # Check if tag already exists (case-sensitive comparison)
            tag_str = f"{category}:{value}"
            tag_exists = any(str(tag) == tag_str for tag in img_data.tags)

            # Only add if tag doesn't exist
            if not tag_exists:
                img_data.add_tag(category, value)
                self.app_manager.save_image_data(img_path, img_data)

        # Clear entry and reload
        self.tag_entry.clear()
        self._load_tags()
        self._update_tag_suggestions()
        self.app_manager.update_project(save=True)

    def _edit_tag(self, item: QTableWidgetItem):
        """Edit an existing tag"""
        if not item:
            return

        # Only allow editing tag column (column 0)
        if item.column() != 0:
            return

        old_tag = item.data(Qt.UserRole)
        if not old_tag:
            return

        # Disconnect any existing itemChanged connections to prevent multiple handlers
        try:
            self.tags_table.itemChanged.disconnect()
        except:
            pass

        # Item is already editable, just trigger edit mode
        self.tags_table.editItem(item)

        # Connect to item changed signal with the old tag stored
        self.tags_table.itemChanged.connect(lambda it: self._on_tag_edited(it, old_tag))

    def _on_tag_edited(self, item: QTableWidgetItem, old_tag: Tag):
        """Handle tag edit completion"""
        try:
            self.tags_table.itemChanged.disconnect()
        except:
            pass

        if not item:
            return

        # Only process changes to tag column (column 0)
        if item.column() != 0:
            return

        new_text = item.text().strip()
        current_view = self.app_manager.get_current_view()
        working_images = current_view.get_working_images() if current_view else []

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

        # Rebuild tag list from all images to reflect deletions
        self.app_manager.rebuild_tag_list()

        # Reload tags
        self._load_tags()
        self._update_tag_suggestions()
        self.app_manager.update_project(save=True)

    def _delete_tag(self):
        """Delete the currently selected tag from all working images"""
        current_row = self.tags_table.currentRow()
        if current_row < 0:
            return

        # Get tag item from column 0
        tag_item = self.tags_table.item(current_row, 0)
        if not tag_item:
            return

        tag_to_delete = tag_item.data(Qt.UserRole)
        if not tag_to_delete:
            return

        current_view = self.app_manager.get_current_view()
        working_images = current_view.get_working_images() if current_view else []

        # Delete tag from all images
        for img_path in working_images:
            img_data = self.app_manager.load_image_data(img_path)
            if tag_to_delete in img_data.tags:
                img_data.remove_tag(tag_to_delete)
                self.app_manager.save_image_data(img_path, img_data)

        # Rebuild tag list from all images to reflect deletions
        self.app_manager.rebuild_tag_list()

        # Reload tags
        self._load_tags()
        self._update_tag_suggestions()
        self.app_manager.update_project(save=True)

    def eventFilter(self, obj, event):
        """Handle keyboard events for inline suggestion navigation and tag deletion"""
        # Check if widgets exist (may be called during initialization)
        if not hasattr(self, 'tags_table') or not hasattr(self, 'tag_entry'):
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

        elif obj == self.tags_table and event.type() == QEvent.KeyPress:
            # Handle Del key on tags table
            if event.key() == Qt.Key_Delete:
                self._delete_tag()
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
        current_view = self.app_manager.get_current_view()
        if not current_view:
            return

        all_images = current_view.get_all_paths()
        active_image = current_view.get_active()

        if not all_images or not active_image:
            return

        try:
            current_idx = all_images.index(active_image)
            new_idx = current_idx + direction

            if 0 <= new_idx < len(all_images):
                current_view.set_active(all_images[new_idx])
                self.app_manager.update_project(save=False)
        except ValueError:
            pass

    def showEvent(self, event):
        """Update when window is shown"""
        super().showEvent(event)
        self._update_tag_suggestions()
        self._load_tags()
