"""
Tag Addition Popup - Dialog for adding tags with fuzzy search
Uses exact same pattern as tag_window.py
"""

from typing import List, Optional
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
)
from PyQt5.QtCore import Qt

from .data_models import Tag
from .utils import fuzzy_search


class TagAdditionPopup(QDialog):
    """
    Dialog for adding tags with fuzzy-searchable category/value fields
    Matches the exact functionality of the tag editor window
    """

    def __init__(
        self, app_manager, initial_tags: Optional[List[Tag]] = None, parent=None
    ):
        super().__init__(parent)
        self.app_manager = app_manager
        self.selected_tags: List[Tag] = initial_tags.copy() if initial_tags else []
        self.all_tags: List[str] = []  # All "category:value" tags
        self._active_entry_field: Optional[str] = None  # Track which field is active

        self._setup_ui()
        self._load_available_tags()
        self._connect_signals()

    def _setup_ui(self):
        """Setup the dialog UI"""
        self.setModal(True)
        self.setWindowTitle("Add Tags")
        self.setMinimumWidth(600)
        self.setMinimumHeight(450)

        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Add Tags to Cropped View")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(title)

        # Category and Tag input fields (same row)
        entry_layout = QHBoxLayout()

        entry_layout.addWidget(QLabel("Category:"))
        self.category_entry = QLineEdit()
        self.category_entry.setPlaceholderText("e.g., style, artist, subject")
        self.category_entry.textChanged.connect(self._on_category_changed)
        entry_layout.addWidget(self.category_entry, 1)

        entry_layout.addWidget(QLabel("Tag:"))
        self.tag_entry = QLineEdit()
        self.tag_entry.setPlaceholderText("e.g., portrait, landscape, oil paint")
        self.tag_entry.textChanged.connect(self._on_tag_entry_changed)
        self.tag_entry.returnPressed.connect(self._add_tag)
        entry_layout.addWidget(self.tag_entry, 2)

        # Add button
        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self._add_tag)
        entry_layout.addWidget(self.add_button)

        layout.addLayout(entry_layout)

        # Shared suggestion list (exact same as tag_window.py)
        self.suggestion_list = QListWidget()
        self.suggestion_list.setMaximumHeight(150)
        self.suggestion_list.setVisible(False)
        self.suggestion_list.itemClicked.connect(self._accept_suggestion)
        self.suggestion_list.setStyleSheet(
            "QListWidget { border: 1px solid palette(mid); }"
        )
        layout.addWidget(self.suggestion_list)

        # Separator
        sep = QLabel("─" * 50)
        layout.addWidget(sep)

        # Selected tags display
        selected_label = QLabel("Selected Tags:")
        selected_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(selected_label)

        self.selected_list = QListWidget()
        self.selected_list.setMaximumHeight(120)
        layout.addWidget(self.selected_list)

        # Remove button for selected tags
        remove_layout = QHBoxLayout()
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self._remove_selected_tag)
        self.remove_button.setEnabled(False)
        remove_layout.addStretch()
        remove_layout.addWidget(self.remove_button)
        layout.addLayout(remove_layout)

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    def _load_available_tags(self):
        """Load all available tags from current project or library view"""
        try:
            print("DEBUG: Loading available tags...")
            current_view = self.app_manager.get_current_view()

            # Check if current view is library view or project view
            library = self.app_manager.get_library()
            is_library_view = (current_view == library) if library else False

            tag_list = None
            if is_library_view:
                print("DEBUG: In Library View - using app_manager.get_tag_list()")
                tag_list = self.app_manager.get_tag_list()
            else:
                print("DEBUG: In Project View")
                if current_view and hasattr(current_view, "tag_list"):
                    tag_list = current_view.tag_list
                    print(f"DEBUG: Got tag_list from current_view: {tag_list}")
                else:
                    # Fallback to app_manager tag list if project doesn't have one?
                    # Or maybe current_view IS None?
                    print("DEBUG: current_view has no tag_list, trying app_manager")
                    tag_list = self.app_manager.get_tag_list()

            if tag_list and hasattr(tag_list, "get_all_tags"):
                self.all_tags = sorted(tag_list.get_all_tags())
                print(f"DEBUG: Loaded {len(self.all_tags)} tags")
            else:
                print("DEBUG: No tag_list found or get_all_tags missing")

        except Exception as e:
            print(f"DEBUG: Error loading tags: {e}")
            import traceback

            traceback.print_exc()

    def _connect_signals(self):
        """Connect signals"""
        self.selected_list.itemSelectionChanged.connect(self._on_selected_tag_selected)

    def _on_category_changed(self, text: str):
        """Handle category field text change - shows existing categories"""
        # Track that category field is active
        self._active_entry_field = "category"

        if not text or text.isspace():
            self.suggestion_list.clear()
            self.suggestion_list.setVisible(False)
            return

        # Extract all unique categories from existing tags
        all_categories = list(
            set(tag_str.split(":", 1)[0] for tag_str in self.all_tags if ":" in tag_str)
        )

        if all_categories:
            # Fuzzy search categories
            matches = fuzzy_search(text.strip(), all_categories)
            if matches:
                self.suggestion_list.clear()
                for match_text, score in matches:
                    self.suggestion_list.addItem(match_text)
                if self.suggestion_list.count() > 0:
                    self.suggestion_list.setCurrentRow(0)
                self.suggestion_list.setVisible(True)
                return

        self.suggestion_list.setVisible(False)

    def _on_tag_entry_changed(self, text: str):
        """Handle tag field text change - suggests tags for the selected category"""
        # Track that tag field is active
        self._active_entry_field = "tag"

        if not text or text.isspace():
            self.suggestion_list.clear()
            self.suggestion_list.setVisible(False)
            return

        category = self.category_entry.text().strip()

        if category:
            # Category is specified - suggest tags for this category only
            category_tags = [
                tag_str.split(":", 1)[1]
                for tag_str in self.all_tags
                if tag_str.startswith(f"{category}:")
            ]

            if category_tags:
                matches = fuzzy_search(text.strip(), category_tags)
                if matches:
                    self.suggestion_list.clear()
                    for match_text, score in matches:
                        self.suggestion_list.addItem(match_text)
                    if self.suggestion_list.count() > 0:
                        self.suggestion_list.setCurrentRow(0)
                    self.suggestion_list.setVisible(True)
                    return
        else:
            # No category specified - suggest all tags
            if self.all_tags:
                matches = fuzzy_search(text.strip(), self.all_tags)
                if matches:
                    self.suggestion_list.clear()
                    for match_text, score in matches:
                        self.suggestion_list.addItem(match_text)
                    if self.suggestion_list.count() > 0:
                        self.suggestion_list.setCurrentRow(0)
                    self.suggestion_list.setVisible(True)
                    return

        self.suggestion_list.setVisible(False)

    def _accept_suggestion(self, item):
        """Accept the selected suggestion and insert into appropriate field"""
        if not item:
            return

        suggestion = item.text()

        # Use the tracked active entry field to determine where to put the suggestion
        if self._active_entry_field == "category":
            self.category_entry.setText(suggestion)
            # Move focus to tag field
            self.tag_entry.setFocus()
            self.tag_entry.selectAll()
            self._active_entry_field = "tag"
        elif self._active_entry_field == "tag":
            self.tag_entry.setText(suggestion)
            self.tag_entry.setFocus()
        else:
            # Fallback: if no field is tracked, check category first
            if not self.category_entry.text().strip():
                self.category_entry.setText(suggestion)
                self.tag_entry.setFocus()
                self._active_entry_field = "tag"
            else:
                self.tag_entry.setText(suggestion)
                self.tag_entry.setFocus()

        # Hide suggestions after acceptance
        self.suggestion_list.clear()
        self.suggestion_list.setVisible(False)

    def _add_tag(self):
        """Add the current category:tag combination"""
        category = self.category_entry.text().strip()
        tag_value = self.tag_entry.text().strip()

        if not category or not tag_value:
            return

        # Create tag object
        tag = Tag(category=category, value=tag_value)

        # Check if tag already exists
        for existing_tag in self.selected_tags:
            if (
                existing_tag.category == tag.category
                and existing_tag.value == tag.value
            ):
                # Already added, just clear fields
                self.category_entry.clear()
                self.tag_entry.clear()
                self.suggestion_list.setVisible(False)
                return

        # Add to selected tags
        self.selected_tags.append(tag)
        self._update_selected_list()

        # Clear inputs for next tag
        self.category_entry.clear()
        self.tag_entry.clear()
        self.suggestion_list.setVisible(False)
        self.category_entry.setFocus()

    def _on_selected_tag_selected(self):
        """Handle selection change in selected tags list"""
        self.remove_button.setEnabled(self.selected_list.currentRow() >= 0)

    def _remove_selected_tag(self):
        """Remove selected tag from the list"""
        current_row = self.selected_list.currentRow()
        if current_row >= 0:
            self.selected_tags.pop(current_row)
            self._update_selected_list()

    def _update_selected_list(self):
        """Update the display of selected tags"""
        self.selected_list.clear()

        for tag in self.selected_tags:
            item_text = f"{tag.category}: {tag.value}"
            item = QListWidgetItem(item_text)
            self.selected_list.addItem(item)

    def get_selected_tags(self) -> List[Tag]:
        """Get the list of selected tags"""
        return self.selected_tags

    def keyPressEvent(self, event):
        """Handle keyboard events"""
        # Allow suggestion list navigation
        if self.suggestion_list.isVisible() and event.key() in (Qt.Key_Up, Qt.Key_Down):
            if event.key() == Qt.Key_Down:
                current_row = self.suggestion_list.currentRow()
                if current_row < self.suggestion_list.count() - 1:
                    self.suggestion_list.setCurrentRow(current_row + 1)
            elif event.key() == Qt.Key_Up:
                current_row = self.suggestion_list.currentRow()
                if current_row > 0:
                    self.suggestion_list.setCurrentRow(current_row - 1)
            return

        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if self.suggestion_list.isVisible() and self.suggestion_list.currentItem():
                # If suggestion list is visible, accept the suggestion
                self._accept_suggestion(self.suggestion_list.currentItem())
            elif self.selected_tags:
                # Only accept if we have selected tags
                self.accept()
            else:
                # Try to add current tag
                self._add_tag()
        else:
            super().keyPressEvent(event)
