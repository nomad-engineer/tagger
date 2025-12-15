"""
Tag Entry Widget - Reusable component for tag entry with fuzzy search and gallery navigation
"""

from typing import List, Optional, Callable
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QEvent, pyqtSignal

from .utils import fuzzy_search


class NavigationLineEdit(QLineEdit):
    """QLineEdit subclass that handles navigation keys for gallery control"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.navigation_callback: Optional[Callable[[int], None]] = None
        self.suggestion_list: Optional[QListWidget] = None

    def set_navigation_callback(self, callback: Callable[[int], None]):
        """Set callback function for navigation events"""
        self.navigation_callback = callback

    def set_suggestion_list(self, suggestion_list: QListWidget):
        """Set reference to suggestion list widget"""
        self.suggestion_list = suggestion_list

    def keyPressEvent(self, event):
        """Handle key press events, intercepting navigation keys"""
        key = event.key()

        # Handle Tab - always accept suggestion if visible
        if key == Qt.Key_Tab:
            if self.suggestion_list and self.suggestion_list.isVisible():
                pass

        # Handle navigation keys - but ONLY if suggestion list is not visible
        if key == Qt.Key_Up:
            # Only navigate gallery if suggestion list is NOT visible
            if not self.suggestion_list or not self.suggestion_list.isVisible():
                if self.navigation_callback:
                    self.navigation_callback(-1)  # Previous image
                return
        elif key == Qt.Key_Down:
            # Only navigate gallery if suggestion list is NOT visible
            if not self.suggestion_list or not self.suggestion_list.isVisible():
                if self.navigation_callback:
                    self.navigation_callback(1)  # Next image
                return

        super().keyPressEvent(event)


class TagEntryWidget(QWidget):
    """
    Reusable widget for adding tags with category/value fields and fuzzy search.

    Signals:
        tag_added(str category, str value): Emitted when a tag is validated and added.
    """

    tag_added = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_tags: List[str] = []
        self._active_entry_field: Optional[str] = None
        self._keep_category = True  # Default behavior: keep category after add

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Entry fields
        entry_layout = QHBoxLayout()

        # Category field
        entry_layout.addWidget(QLabel("Category:"))
        self.category_entry = NavigationLineEdit()
        self.category_entry.setPlaceholderText("e.g., artist")
        self.category_entry.textChanged.connect(self._on_category_changed)
        self.category_entry.installEventFilter(self)
        entry_layout.addWidget(self.category_entry, 1)

        # Tag field
        entry_layout.addWidget(QLabel("Tag:"))
        self.tag_entry = NavigationLineEdit()
        self.tag_entry.setPlaceholderText("e.g., value")
        self.tag_entry.textChanged.connect(self._on_tag_entry_changed)
        self.tag_entry.returnPressed.connect(self._on_add_clicked)
        self.tag_entry.installEventFilter(self)
        entry_layout.addWidget(self.tag_entry, 2)

        # Add button
        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self._on_add_clicked)
        entry_layout.addWidget(self.add_btn)

        layout.addLayout(entry_layout)

        # Inline suggestion list
        self.suggestion_list = QListWidget()
        self.suggestion_list.setMaximumHeight(150)
        self.suggestion_list.setVisible(False)
        self.suggestion_list.itemClicked.connect(self._accept_suggestion)
        self.suggestion_list.setStyleSheet(
            "QListWidget { border: 1px solid palette(mid); }"
        )

        # Connect suggestion list to entry fields so they can check visibility
        self.category_entry.set_suggestion_list(self.suggestion_list)
        self.tag_entry.set_suggestion_list(self.suggestion_list)

        layout.addWidget(self.suggestion_list)

    def set_tags(self, tags: List[str]):
        """Set the list of available tags for autocomplete"""
        self.all_tags = tags

    def set_navigation_callback(self, callback: Callable[[int], None]):
        """Set the callback for gallery navigation (Up/Down)"""
        self.category_entry.set_navigation_callback(callback)
        self.tag_entry.set_navigation_callback(callback)

    def clear_all(self):
        """Clear both input fields"""
        self.category_entry.clear()
        self.tag_entry.clear()
        self.suggestion_list.setVisible(False)

    def cleanup_after_add(self):
        """Clear inputs based on keep_category mode"""
        self.tag_entry.clear()
        if not self._keep_category:
            self.category_entry.clear()

        self.suggestion_list.setVisible(False)
        self.tag_entry.setFocus()

    def set_keep_category_mode(self, keep: bool):
        """If True, category field is NOT cleared after adding a tag"""
        self._keep_category = keep

    def get_category(self) -> str:
        return self.category_entry.text().strip()

    def get_value(self) -> str:
        return self.tag_entry.text().strip()

    def _on_category_changed(self, text: str):
        self._active_entry_field = "category"
        if not text:
            self.suggestion_list.setVisible(False)
            return

        # Extract unique categories
        all_categories = list(
            set(t.split(":", 1)[0] for t in self.all_tags if ":" in t)
        )
        self._update_suggestions(text, all_categories)

    def _on_tag_entry_changed(self, text: str):
        self._active_entry_field = "tag"
        if not text:
            self.suggestion_list.setVisible(False)
            return

        category = self.category_entry.text().strip()
        if category:
            # Suggest tags for this category
            candidates = [
                t.split(":", 1)[1]
                for t in self.all_tags
                if t.startswith(f"{category}:")
            ]
        else:
            # Suggest full tags
            candidates = self.all_tags

        self._update_suggestions(text, candidates)

    def _update_suggestions(self, text: str, candidates: List[str]):
        matches = fuzzy_search(text.strip(), candidates)
        if matches:
            self.suggestion_list.clear()
            for match_text, _ in matches:
                self.suggestion_list.addItem(match_text)
            if self.suggestion_list.count() > 0:
                self.suggestion_list.setCurrentRow(0)
            self.suggestion_list.setVisible(True)
        else:
            self.suggestion_list.setVisible(False)

    def _accept_suggestion(self, item):
        if not item:
            return

        suggestion = item.text()

        if self._active_entry_field == "category":
            self.category_entry.setText(suggestion)
            self.tag_entry.setFocus()
            self.tag_entry.selectAll()
            self._active_entry_field = "tag"
        else:
            self.tag_entry.setText(suggestion)
            self.tag_entry.setFocus()

        self.suggestion_list.setVisible(False)

    def _on_add_clicked(self):
        category = self.category_entry.text().strip()
        value = self.tag_entry.text().strip()

        if not value:
            QMessageBox.warning(self, "No Tag", "Please enter a tag value.")
            return
        if not category:
            QMessageBox.warning(self, "No Category", "Please specify a category.")
            return

        # Emit signal - Parent responsible for clearing inputs on success
        self.tag_added.emit(category, value)

    def eventFilter(self, obj, event):
        """Handle Tab and navigation for the suggestion list"""
        if (
            obj == self.tag_entry or obj == self.category_entry
        ) and event.type() == QEvent.KeyPress:
            if self.suggestion_list.isVisible() and self.suggestion_list.count() > 0:
                key = event.key()
                if key == Qt.Key_Down:
                    row = self.suggestion_list.currentRow()
                    if row < self.suggestion_list.count() - 1:
                        self.suggestion_list.setCurrentRow(row + 1)
                    return True
                elif key == Qt.Key_Up:
                    row = self.suggestion_list.currentRow()
                    if row > 0:
                        self.suggestion_list.setCurrentRow(row - 1)
                    return True
                elif key == Qt.Key_Tab:
                    self._accept_suggestion(self.suggestion_list.currentItem())
                    return True
                elif key == Qt.Key_Escape:
                    self.suggestion_list.setVisible(False)
                    return True
        return super().eventFilter(obj, event)
