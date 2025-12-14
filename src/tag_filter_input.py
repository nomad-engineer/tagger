"""
TagFilterInput - Reusable tag filter input widget with fuzzy search
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QListWidget
from PyQt5.QtCore import Qt, QEvent, pyqtSignal

from .utils import fuzzy_search


class TagFilterInput(QWidget):
    """Reusable tag filter input widget with inline fuzzy search suggestions

    This widget provides:
    - Input field for filter expressions
    - Inline suggestion list with fuzzy search
    - Automatic quote wrapping when accepting suggestions
    - Keyboard navigation (Up/Down/Tab/Escape)
    - Support for filter parser syntax (AND/OR/NOT)

    Signals:
        filterTextChanged: Emitted when filter text changes
        filterApplied: Emitted when Enter is pressed without suggestion selected
    """

    filterTextChanged = pyqtSignal(str)  # Emitted on text change
    filterApplied = pyqtSignal(str)  # Emitted when Enter pressed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_tags = []
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Filter input field
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Enter filter expression...")
        self.filter_input.textChanged.connect(self._on_text_changed)
        self.filter_input.returnPressed.connect(self._on_return_pressed)
        self.filter_input.installEventFilter(self)
        layout.addWidget(self.filter_input)

        # Inline suggestion list
        self.suggestion_list = QListWidget()
        self.suggestion_list.setMaximumHeight(150)
        self.suggestion_list.setVisible(False)
        self.suggestion_list.itemClicked.connect(self._accept_suggestion)
        self.suggestion_list.setStyleSheet(
            "QListWidget { border: 1px solid palette(mid); }"
        )
        layout.addWidget(self.suggestion_list)

    def set_tags_list(self, tags):
        """Set the list of tags for fuzzy search suggestions

        Args:
            tags: List of tag strings (e.g., ["class:lake", "setting:mountain"])
        """
        self.all_tags = tags

    def get_filter_text(self):
        """Get current filter text

        Returns:
            str: Current filter expression
        """
        return self.filter_input.text().strip()

    def set_filter_text(self, text):
        """Set filter text

        Args:
            text: Filter expression to set
        """
        self.filter_input.setText(text)

    def clear_filter(self):
        """Clear filter text and hide suggestions"""
        self.filter_input.clear()
        self.suggestion_list.clear()
        self.suggestion_list.setVisible(False)

    def _on_text_changed(self, text):
        """Handle filter text change - update fuzzy search suggestions"""
        # Emit signal
        self.filterTextChanged.emit(text)

        # Update suggestions
        self._update_suggestions(text)

    def _update_suggestions(self, text):
        """Update inline suggestion list with fuzzy search results"""
        # Get the last word being typed
        words = text.split()
        if not words:
            self.suggestion_list.clear()
            self.suggestion_list.setVisible(False)
            return

        last_word = words[-1]

        # Skip logical operators
        if last_word.upper() in ["AND", "OR", "NOT"] or len(last_word) == 0:
            self.suggestion_list.clear()
            self.suggestion_list.setVisible(False)
            return

        # Perform fuzzy search on tags
        if self.all_tags:
            matches = fuzzy_search(last_word, self.all_tags)

            if matches:
                # Show all matches in suggestion list
                self.suggestion_list.clear()
                for match_text, score in matches:
                    self.suggestion_list.addItem(match_text)

                # DO NOT auto-select first item - user must press Down to enter list
                self.suggestion_list.setCurrentRow(-1)
                self.suggestion_list.setVisible(True)
            else:
                self.suggestion_list.clear()
                self.suggestion_list.setVisible(False)
        else:
            # Show helpful message when no tags available
            self.suggestion_list.clear()
            self.suggestion_list.addItem("(No tags available)")
            self.suggestion_list.setVisible(True)

    def _on_return_pressed(self):
        """Handle Return key when not in suggestion list"""
        # Only emit if no suggestion is selected
        if self.suggestion_list.currentRow() == -1:
            self.filterApplied.emit(self.get_filter_text())

    def eventFilter(self, obj, event):
        """Handle keyboard events for inline suggestion navigation"""
        if obj == self.filter_input and event.type() == QEvent.KeyPress:
            if self.suggestion_list.isVisible() and self.suggestion_list.count() > 0:
                key = event.key()

                if key == Qt.Key_Down:
                    # Move selection down in suggestion list, or enter list if no selection
                    current_row = self.suggestion_list.currentRow()
                    if current_row == -1:
                        # Enter the list by selecting first item
                        self.suggestion_list.setCurrentRow(0)
                    elif current_row < self.suggestion_list.count() - 1:
                        self.suggestion_list.setCurrentRow(current_row + 1)
                    return True

                elif key == Qt.Key_Up:
                    # Move selection up in suggestion list
                    current_row = self.suggestion_list.currentRow()
                    if current_row > 0:
                        self.suggestion_list.setCurrentRow(current_row - 1)
                    elif current_row == 0:
                        # Exit the list by clearing selection
                        self.suggestion_list.setCurrentRow(-1)
                    return True

                elif key == Qt.Key_Return:
                    # Enter key with selected item - accept suggestion
                    current_row = self.suggestion_list.currentRow()
                    if current_row >= 0:
                        current_item = self.suggestion_list.currentItem()
                        if current_item:
                            self._accept_suggestion(current_item)
                            return True
                    # No selection - let returnPressed signal handle it
                    return False

                elif key == Qt.Key_Tab:
                    # Tab always accepts suggestion if one is selected
                    current_row = self.suggestion_list.currentRow()
                    if current_row >= 0:
                        current_item = self.suggestion_list.currentItem()
                        if current_item:
                            self._accept_suggestion(current_item)
                            return True

                elif key == Qt.Key_Escape:
                    # Hide suggestions
                    self.suggestion_list.setVisible(False)
                    return True

        return super().eventFilter(obj, event)

    def _accept_suggestion(self, item):
        """Accept the selected suggestion and insert into filter input

        Always wraps the tag in quotes to handle spaces correctly.
        """
        if not item:
            return

        suggestion = item.text()

        # Skip if it's the placeholder message
        if suggestion.startswith("(No tags"):
            return

        # Get current text
        current_text = self.filter_input.text()
        words = current_text.split()

        # Wrap suggestion in quotes (always, per user requirement)
        quoted_suggestion = f'"{suggestion}"'

        # Replace the last word with the quoted suggestion
        if words:
            words[-1] = quoted_suggestion
            new_text = " ".join(words) + " "  # Add space after for next word
        else:
            new_text = quoted_suggestion + " "

        self.filter_input.setText(new_text)
        self.filter_input.setFocus()

        # Hide suggestions after acceptance
        self.suggestion_list.clear()
        self.suggestion_list.setVisible(False)

    def focusInEvent(self, event):
        """Focus input field when widget receives focus"""
        super().focusInEvent(event)
        self.filter_input.setFocus()
