"""
SavedFiltersDialog - Self-contained modal dialog for filtering with saved filters
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QListWidgetItem, QMessageBox, QWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from .tag_filter_input import TagFilterInput
from .filter_parser import evaluate_filter


class SavedFiltersDialog(QDialog):
    """Self-contained filter dialog

    Includes filter input, saved filters management, and apply functionality.
    Dialog auto-closes when filter is applied.
    """

    def __init__(self, app_manager, parent=None, current_filter="", mode="images"):
        """Initialize dialog

        Args:
            app_manager: Application manager instance
            parent: Parent widget
            current_filter: Current active filter to display in input field
            mode: "images" to filter images, "tags" to just return filter expression
        """
        super().__init__(parent)
        self.app_manager = app_manager
        self.all_tags = []
        self.current_filter = current_filter
        self.mode = mode  # "images" or "tags"
        self.selected_filter_expression = ""  # For tags mode

        # Storage keys based on mode
        if self.mode == "images":
            self.saved_filters_key = "image_saved_filters"
            self.default_filter_key = "image_default_filter"
        else:  # tags
            self.saved_filters_key = "tag_saved_filters"
            self.default_filter_key = "tag_default_filter"

        self.setWindowTitle("Filter")
        self.setMinimumSize(600, 500)
        self.setModal(True)

        self._setup_ui()
        self._load_filters()
        self._update_tag_suggestions()

        # Set current filter in input field if provided
        if self.current_filter:
            self.filter_input.set_filter_text(self.current_filter)

    def _setup_ui(self):
        """Setup UI components"""
        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel(
            "Filter Syntax:\n"
            "• Exact match: \"class:lake\" (matches only 'class:lake')\n"
            "• Wildcard: \"class:lake*\" (matches 'class:lake', 'class:lakeside', etc.)\n"
            "• Operators: AND, OR, NOT\n"
            "• Grouping: (\"class:lake\" OR \"class:river\") AND \"setting:mountain\""
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Filter input with TagFilterInput widget
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))

        self.filter_input = TagFilterInput()
        self.filter_input.filterTextChanged.connect(self._on_filter_changed)
        self.filter_input.filterApplied.connect(self._apply_filter)
        filter_layout.addWidget(self.filter_input, 1)

        layout.addLayout(filter_layout)

        # Result label showing match count
        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.result_label)

        # Apply and Clear buttons row
        apply_layout = QHBoxLayout()
        apply_layout.addStretch()

        clear_btn = QPushButton("Clear Filter")
        clear_btn.clicked.connect(self._clear_filter)
        apply_layout.addWidget(clear_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._apply_filter)
        apply_layout.addWidget(apply_btn)

        layout.addLayout(apply_layout)

        # Separator
        separator = QLabel()
        separator.setStyleSheet("border-top: 1px solid palette(mid); margin: 10px 0;")
        layout.addWidget(separator)

        # Saved filters section
        layout.addWidget(QLabel("Saved Filters:"))

        saved_help = QLabel(
            "Save frequently used filters for quick access. "
            "Set a default filter to auto-apply when opening the project."
        )
        saved_help.setWordWrap(True)
        saved_help.setStyleSheet("color: gray; font-size: 9px; padding-bottom: 5px;")
        layout.addWidget(saved_help)

        self.filters_list = QListWidget()
        self.filters_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.filters_list.itemDoubleClicked.connect(self._load_and_apply_selected)
        layout.addWidget(self.filters_list)

        # Saved filters management buttons
        buttons_row1 = QHBoxLayout()

        self.save_btn = QPushButton("Save Current")
        self.save_btn.clicked.connect(self._save_current_filter)
        buttons_row1.addWidget(self.save_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete_selected)
        self.delete_btn.setEnabled(False)
        buttons_row1.addWidget(self.delete_btn)

        self.default_btn = QPushButton("Set as Default")
        self.default_btn.clicked.connect(self._set_as_default)
        self.default_btn.setEnabled(False)
        buttons_row1.addWidget(self.default_btn)

        layout.addLayout(buttons_row1)

        # Load and Close buttons
        buttons_row2 = QHBoxLayout()
        buttons_row2.addStretch()

        self.load_btn = QPushButton("Load && Apply")
        self.load_btn.setToolTip("Load selected filter and apply it immediately")
        self.load_btn.clicked.connect(self._load_and_apply_selected)
        self.load_btn.setEnabled(False)
        buttons_row2.addWidget(self.load_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        buttons_row2.addWidget(close_btn)

        layout.addLayout(buttons_row2)

    def _update_tag_suggestions(self):
        """Update filter input with all tags from project"""
        self.all_tags = self.app_manager.get_tag_list().get_all_full_tags()
        self.filter_input.set_tags_list(self.all_tags)

    def _on_filter_changed(self, text):
        """Handle filter text change - clear result label"""
        if not text:
            self.result_label.setText("")

    def _clear_filter(self):
        """Clear the filter and close dialog"""
        if self.mode == "images":
            # Clear image filter
            self.app_manager.set_filtered_view(None)
            self.app_manager.current_filter_expression = ""
        else:
            # Tags mode - just return empty filter
            self.selected_filter_expression = ""

        self.result_label.setText("")
        self.accept()

    def _apply_filter(self):
        """Apply the filter expression (behavior depends on mode)"""
        filter_text = self.filter_input.get_filter_text()

        # Tags mode - just store filter expression and close
        if self.mode == "tags":
            self.selected_filter_expression = filter_text
            self.accept()
            return

        # Images mode - filter images
        image_list = self.app_manager.get_image_list()
        if image_list is None:
            QMessageBox.warning(
                self,
                "No Images",
                "No images available to filter."
            )
            return

        if not filter_text:
            # No filter, clear filtered view
            self.app_manager.set_filtered_view(None)
            self.app_manager.current_filter_expression = ""
            self.accept()
            return

        # Get all images from main image list
        all_images = image_list.get_all_paths()

        # Filter images using parser
        filtered = []
        for img_path in all_images:
            try:
                img_data = self.app_manager.load_image_data(img_path)
                img_tag_strs = [str(tag) for tag in img_data.tags]

                # Use filter parser with exact/wildcard matching
                result = evaluate_filter(filter_text, img_tag_strs)

                if result:
                    filtered.append(img_path)
            except ValueError as e:
                # Invalid filter expression - show error to user
                self.result_label.setText(f"Invalid filter: {e}")
                self.result_label.setStyleSheet("color: #d9534f; font-style: italic;")
                return
            except Exception as e:
                print(f"ERROR: Error filtering image {img_path}: {e}")
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
        base_dir = image_list._base_dir
        if base_dir:
            filtered_view = ImageList.create_filtered(base_dir, filtered)
            self.app_manager.set_filtered_view(filtered_view)
            self.app_manager.current_filter_expression = filter_text

        # Close dialog after applying filter
        self.accept()

    def _load_filters(self):
        """Load saved filters from project or library"""
        self.filters_list.clear()

        # Load from library or project depending on view mode
        if self.app_manager.current_view_mode == "library":
            library = self.app_manager.get_library()
            if not library:
                print(f"[DEBUG] No library found for mode {self.mode}")
                return
            filters_dict = library.filters
        else:
            project = self.app_manager.get_project()
            if not project:
                print(f"[DEBUG] No project found for mode {self.mode}")
                return
            filters_dict = project.filters

        saved_filters = filters_dict.get(self.saved_filters_key, [])
        default_filter = filters_dict.get(self.default_filter_key, "")

        print(f"[DEBUG] Mode: {self.mode}, Loading from key: {self.saved_filters_key}")
        print(f"[DEBUG] View mode: {self.app_manager.current_view_mode}")
        print(f"[DEBUG] Loading {len(saved_filters)} saved filters")
        print(f"[DEBUG] Saved filters: {saved_filters}")
        print(f"[DEBUG] Default filter: {default_filter}")

        for filter_text in saved_filters:
            print(f"[DEBUG] Adding filter to list: {filter_text}")

            # Create custom item widget with indicator if default
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(5, 2, 5, 2)

            # Default indicator
            if filter_text == default_filter:
                default_indicator = QLabel("⭐")
                default_indicator.setToolTip("Default filter")
                font = QFont()
                font.setPointSize(12)
                default_indicator.setFont(font)
                item_layout.addWidget(default_indicator)

            # Filter text
            label = QLabel(filter_text)
            label.setWordWrap(False)
            item_layout.addWidget(label, 1)

            # Create list item
            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, filter_text)
            self.filters_list.addItem(list_item)
            self.filters_list.setItemWidget(list_item, item_widget)
            print(f"[DEBUG] Filter added, list now has {self.filters_list.count()} items")

    def _on_selection_changed(self):
        """Handle selection change - enable/disable buttons"""
        has_selection = bool(self.filters_list.selectedItems())
        self.delete_btn.setEnabled(has_selection)
        self.default_btn.setEnabled(has_selection)
        self.load_btn.setEnabled(has_selection)

    def _save_current_filter(self):
        """Save current filter to project"""
        filter_text = self.filter_input.get_filter_text()
        if not filter_text:
            QMessageBox.information(
                self,
                "No Filter",
                "Enter a filter expression first."
            )
            return

        project = self.app_manager.get_project()

        # Get existing saved filters for this mode
        if self.saved_filters_key not in project.filters:
            project.filters[self.saved_filters_key] = []

        # Check if already saved
        if filter_text in project.filters[self.saved_filters_key]:
            QMessageBox.information(
                self,
                "Already Saved",
                "This filter is already in your saved filters list."
            )
            return

        # Add filter
        print(f"[DEBUG] Saving filter to {self.saved_filters_key}: {filter_text}")
        print(f"[DEBUG] View mode: {self.app_manager.current_view_mode}")

        # Save to the appropriate location based on view mode
        if self.app_manager.current_view_mode == "library":
            # In library view - save to library
            library = self.app_manager.get_library()
            if library:
                if self.saved_filters_key not in library.filters:
                    library.filters[self.saved_filters_key] = []
                library.filters[self.saved_filters_key].append(filter_text)
                library.save()
                print(f"[DEBUG] Library filter saved to: {library.library_file}")
        else:
            # In project view - save to project
            if self.saved_filters_key not in project.filters:
                project.filters[self.saved_filters_key] = []
            project.filters[self.saved_filters_key].append(filter_text)
            if project.project_file:
                project.save()
                print(f"[DEBUG] Project filter saved to: {project.project_file}")
            else:
                print(f"[DEBUG] ERROR: No project_file set!")

        # Reload list
        self._load_filters()

        # Show confirmation
        QMessageBox.information(
            self,
            "Filter Saved",
            "Filter has been saved successfully."
        )

    def _delete_selected(self):
        """Delete selected filter"""
        selected_items = self.filters_list.selectedItems()
        if not selected_items:
            return

        filter_text = selected_items[0].data(Qt.UserRole)

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Filter",
            f"Are you sure you want to delete this filter?\n\n{filter_text}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Delete from the appropriate location based on view mode
        if self.app_manager.current_view_mode == "library":
            library = self.app_manager.get_library()
            if library:
                if self.saved_filters_key in library.filters and filter_text in library.filters[self.saved_filters_key]:
                    library.filters[self.saved_filters_key].remove(filter_text)
                if library.filters.get(self.default_filter_key) == filter_text:
                    library.filters[self.default_filter_key] = ""
                library.save()
        else:
            project = self.app_manager.get_project()
            if self.saved_filters_key in project.filters and filter_text in project.filters[self.saved_filters_key]:
                project.filters[self.saved_filters_key].remove(filter_text)
            if project.filters.get(self.default_filter_key) == filter_text:
                project.filters[self.default_filter_key] = ""
            if project.project_file:
                project.save()

        # Reload list
        self._load_filters()

    def _set_as_default(self):
        """Set selected filter as default"""
        selected_items = self.filters_list.selectedItems()
        if not selected_items:
            return

        filter_text = selected_items[0].data(Qt.UserRole)

        print(f"[DEBUG] Setting default filter for {self.default_filter_key}: {filter_text}")

        # Set default in the appropriate location based on view mode
        if self.app_manager.current_view_mode == "library":
            library = self.app_manager.get_library()
            if library:
                library.filters[self.default_filter_key] = filter_text
                library.save()
        else:
            project = self.app_manager.get_project()
            project.filters[self.default_filter_key] = filter_text
            if project.project_file:
                project.save()

        # Reload list to show star indicator
        self._load_filters()

        # Show confirmation
        QMessageBox.information(
            self,
            "Default Set",
            "This filter will automatically apply when opening the project."
        )

    def _load_and_apply_selected(self, item=None):
        """Load selected filter, apply it immediately, and close dialog"""
        selected_items = self.filters_list.selectedItems()
        if not selected_items:
            return

        filter_text = selected_items[0].data(Qt.UserRole)

        # Set filter text in input
        self.filter_input.set_filter_text(filter_text)

        # Apply filter and close
        self._apply_filter()

    def get_filter_expression(self):
        """Get the selected filter expression (for tags mode)

        Returns:
            str: Filter expression selected by user
        """
        return self.selected_filter_expression
