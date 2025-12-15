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
from .tag_entry_widget import TagEntryWidget
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

        # Tag Entry Widget
        self.tag_entry_widget = TagEntryWidget()
        self.tag_entry_widget.tag_added.connect(self._add_tag)
        self.tag_entry_widget.set_keep_category_mode(
            False
        )  # Clear both fields after add
        layout.addWidget(self.tag_entry_widget)

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
                self.tag_entry_widget.set_tags(self.all_tags)
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

    def _add_tag(self, category: str, value: str):
        """Add the current category:tag combination"""
        if not category or not value:
            return

        # Check if tag already exists
        for existing_tag in self.selected_tags:
            if existing_tag.category == category and existing_tag.value == value:
                # Already added, just clear fields
                self.tag_entry_widget.cleanup_after_add()
                return

        # Add to selected tags
        tag = Tag(category=category, value=value)
        self.selected_tags.append(tag)
        self._update_selected_list()

        # Clear inputs
        self.tag_entry_widget.cleanup_after_add()

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
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
