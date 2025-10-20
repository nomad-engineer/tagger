"""
Filter Window - Filter images based on tags with fuzzy search
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QScrollArea
)
from PyQt5.QtCore import Qt, QEvent
from pathlib import Path

from .utils import fuzzy_search
from .data_models import ImageData
from .filter_parser import evaluate_filter


class Filter(QWidget):
    """Filter window for filtering images by tags"""

    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self.all_tags = []

        self.setWindowTitle("Filter")
        self.setMinimumSize(300, 200)
        self.resize(500, 400)  # Default size, but can be resized smaller

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
        self.app_manager.project_changed.connect(self._load_saved_filters)
        self.app_manager.project_changed.connect(self._update_tag_suggestions)

        # Initial load
        self._load_saved_filters()
        self._update_tag_suggestions()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Instructions
        instructions = QLabel(
            "Filter Syntax:\n"
            "• Exact match: class:lake (matches only 'class:lake')\n"
            "• Wildcard: class:lake* (matches 'class:lake', 'class:lakeside', etc.)\n"
            "• Operators: AND, OR, NOT\n"
            "• Grouping: (class:lake OR class:river) AND setting:mountain"
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(instructions)

        # Filter string entry
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))

        self.filter_input = QLineEdit()
        self.filter_input.textChanged.connect(self._on_filter_changed)
        self.filter_input.returnPressed.connect(self._apply_filter)
        self.filter_input.installEventFilter(self)  # Install event filter for custom key handling
        filter_layout.addWidget(self.filter_input)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply_filter)
        filter_layout.addWidget(apply_btn)

        layout.addLayout(filter_layout)

        # Filter result label
        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.result_label)

        # Inline suggestion list (replaces QCompleter popup)
        self.suggestion_list = QListWidget()
        self.suggestion_list.setMaximumHeight(150)
        self.suggestion_list.setVisible(False)
        self.suggestion_list.itemClicked.connect(self._accept_suggestion)
        # Use system theme colors - only add border
        self.suggestion_list.setStyleSheet("QListWidget { border: 1px solid palette(mid); }")
        layout.addWidget(self.suggestion_list)

        # Save filter button
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        save_btn = QPushButton("Save Filter")
        save_btn.clicked.connect(self._save_filter)
        save_layout.addWidget(save_btn)
        layout.addLayout(save_layout)

        # Saved filters list
        layout.addWidget(QLabel("Saved Filters:"))
        self.saved_filters_list = QListWidget()
        self.saved_filters_list.itemClicked.connect(self._load_filter)
        layout.addWidget(self.saved_filters_list)

    def _update_tag_suggestions(self):
        """Update autocomplete suggestions with all tags in project"""
        # Get only full tags (not categories) for suggestions
        self.all_tags = self.app_manager.get_tag_list().get_all_full_tags()

    def _on_filter_changed(self, text: str):
        """Handle filter text change for fuzzy search - updates inline suggestion list"""
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

    def _apply_filter(self):
        """Apply the filter expression to images"""
        filter_text = self.filter_input.text().strip()

        image_list = self.app_manager.get_image_list()
        if image_list is None:
            return

        if not filter_text:
            # No filter, clear filtered view
            self.result_label.setText("")
            self.app_manager.set_filtered_view(None)
            return

        # Get all images from main image list
        all_images = image_list.get_all_paths()

        # Filter images using new parser
        filtered = []
        for img_path in all_images:
            try:
                img_data = self.app_manager.load_image_data(img_path)
                img_tag_strs = [str(tag) for tag in img_data.tags]

                # Use new filter parser with exact/wildcard matching
                result = evaluate_filter(filter_text, img_tag_strs)

                if result:
                    filtered.append(img_path)
            except ValueError as e:
                # Invalid filter expression - show error to user
                print(f"ERROR: Invalid filter expression: {e}")
                continue

        # Update result label
        if len(filtered) == 0:
            self.result_label.setText("No images match the filter")
            self.result_label.setStyleSheet("color: #d9534f; font-style: italic;")  # Red
        elif len(filtered) == 1:
            self.result_label.setText("1 image matches")
            self.result_label.setStyleSheet("color: #5cb85c; font-style: italic;")  # Green
        else:
            self.result_label.setText(f"{len(filtered)} images match")
            self.result_label.setStyleSheet("color: #5cb85c; font-style: italic;")  # Green

        # Create filtered ImageList view
        from .data_models import ImageList
        base_dir = self.app_manager.get_project().get_base_directory()
        if base_dir:
            filtered_view = ImageList.create_filtered(base_dir, filtered)
            self.app_manager.set_filtered_view(filtered_view)

    def _save_filter(self):
        """Save the current filter to the project"""
        filter_text = self.filter_input.text().strip()
        if not filter_text:
            return

        project = self.app_manager.get_project()

        # Get existing saved filters
        if "saved_filters" not in project.filters:
            project.filters["saved_filters"] = []

        # Add filter if not already saved
        if filter_text not in project.filters["saved_filters"]:
            project.filters["saved_filters"].append(filter_text)
            self.app_manager.update_project(save=True)
            self._load_saved_filters()

    def _load_saved_filters(self):
        """Load saved filters from project"""
        self.saved_filters_list.clear()

        project = self.app_manager.get_project()
        if not project.project_file:
            return

        saved_filters = project.filters.get("saved_filters", [])

        for filter_text in saved_filters:
            # Create item with delete button
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(2, 2, 2, 2)

            label = QLabel(filter_text)
            item_layout.addWidget(label)

            delete_btn = QPushButton("×")
            delete_btn.setMaximumWidth(30)
            delete_btn.clicked.connect(lambda checked, f=filter_text: self._delete_filter(f))
            item_layout.addWidget(delete_btn)

            from PyQt5.QtWidgets import QListWidgetItem
            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, filter_text)
            self.saved_filters_list.addItem(list_item)
            self.saved_filters_list.setItemWidget(list_item, item_widget)

    def _load_filter(self, item):
        """Load a saved filter into the input"""
        filter_text = item.data(Qt.UserRole)
        if filter_text:
            self.filter_input.setText(filter_text)
            self._apply_filter()

    def _delete_filter(self, filter_text: str):
        """Delete a saved filter"""
        project = self.app_manager.get_project()
        if "saved_filters" in project.filters and filter_text in project.filters["saved_filters"]:
            project.filters["saved_filters"].remove(filter_text)
            self.app_manager.update_project(save=True)
            self._load_saved_filters()

    def eventFilter(self, obj, event):
        """Handle keyboard events for inline suggestion navigation"""
        if obj == self.filter_input and event.type() == QEvent.KeyPress:
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

                elif key == Qt.Key_Tab or key == Qt.Key_Return:
                    # Accept current suggestion
                    if event.key() == Qt.Key_Return and self.filter_input.text().strip():
                        # If Enter and there's text, check if we should accept suggestion or apply filter
                        current_item = self.suggestion_list.currentItem()
                        if current_item:
                            self._accept_suggestion(current_item)
                            return True
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

        return super().eventFilter(obj, event)

    def _accept_suggestion(self, item):
        """Accept the selected suggestion and insert into filter input"""
        if not item:
            return

        suggestion = item.text()

        # Get current text and cursor position
        current_text = self.filter_input.text()
        words = current_text.split()

        # Replace the last word with the suggestion
        if words:
            words[-1] = suggestion
            new_text = " ".join(words) + " "  # Add space after for next word
        else:
            new_text = suggestion + " "

        self.filter_input.setText(new_text)
        self.filter_input.setFocus()

        # Hide suggestions after acceptance
        self.suggestion_list.clear()
        self.suggestion_list.setVisible(False)

    def showEvent(self, event):
        """Update tags when window is shown"""
        super().showEvent(event)
        self._update_tag_suggestions()
