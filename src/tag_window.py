"""
Tag Window - View and edit tags for selected images with fuzzy search
"""

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QGroupBox,
    QCheckBox,
    QComboBox,
    QTextEdit,
    QSplitter,
    QScrollArea,
    QFrame,
    QMessageBox,
    QDialog,
    QProgressBar,
    QPushButton,
    QDialogButtonBox,
    QCompleter,
    QAbstractItemView,
    QMenu,
    QAction,
)
from PyQt5.QtCore import Qt, QEvent


from typing import List

from .tag_entry_widget import TagEntryWidget
from .utils import fuzzy_search
from .data_models import ImageData, Tag
from .saved_filters_dialog import SavedFiltersDialog
from .filter_parser import evaluate_filter


class TagWindow(QWidget):
    """Tag editor window for viewing and modifying tags"""

    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self.all_tags = []
        self._updating = False
        self.quick_add_tags = []  # Parsed list of tags for quick add
        self._multi_select_warned = False  # Track if we've shown multi-select warning
        self._active_filter = ""  # Track active filter expression for tags table
        self._stored_selection = set()  # Store selection for multi-edit operations
        self._active_entry_field = (
            None  # Track which entry field is currently active (category or tag)
        )

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
        self.app_manager.project_changed.connect(self._load_default_filter)
        self.app_manager.library_changed.connect(self._load_tags)
        self.app_manager.library_changed.connect(self._update_tag_suggestions)
        self.app_manager.library_changed.connect(self._update_window_title)

        # Initial load
        self._update_tag_suggestions()
        self._load_tags()
        self._update_window_title()
        self._load_default_filter()

    def _update_window_title(self):
        """Update window title to show library/project name"""
        library = self.app_manager.get_library()
        project = self.app_manager.get_project()

        # Build title
        title_parts = ["Tag Editor"]

        # Add view name
        if (
            self.app_manager.current_view_mode == "project"
            and project
            and project.project_name
        ):
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

        # Tag Entry Widget
        self.tag_entry_widget = TagEntryWidget()
        self.tag_entry_widget.tag_added.connect(self._add_tag)
        self.tag_entry_widget.set_navigation_callback(self._change_active_image)
        layout.addWidget(self.tag_entry_widget)

        # Quick Add section (expandable)
        self.quick_add_group = QGroupBox("Quick Add")
        self.quick_add_group.setCheckable(True)
        self.quick_add_group.setChecked(False)
        self.quick_add_group.toggled.connect(self._on_quick_add_toggled)
        quick_add_layout = QVBoxLayout()

        # Create a container widget for the contents so we can hide/show them
        self.quick_add_contents = QWidget()
        contents_layout = QVBoxLayout(self.quick_add_contents)
        contents_layout.setContentsMargins(0, 0, 0, 0)

        # Input field for comma-separated tags
        quick_input_layout = QHBoxLayout()
        quick_input_layout.addWidget(QLabel("Tags:"))
        self.quick_add_input = QLineEdit()
        self.quick_add_input.setPlaceholderText(
            "category1, category2:tag1, category3:tag2"
        )
        self.quick_add_input.textChanged.connect(self._parse_quick_add_tags)
        quick_input_layout.addWidget(self.quick_add_input)
        contents_layout.addLayout(quick_input_layout)

        # Help text
        quick_help = QLabel(
            "Enter categories or tags separated by commas. Categories expand to all their tags."
        )
        quick_help.setStyleSheet("color: gray; font-size: 9px;")
        contents_layout.addWidget(quick_help)

        # List of quick add tags with checkboxes
        self.quick_add_list = QListWidget()
        self.quick_add_list.setMaximumHeight(200)
        self.quick_add_list.itemChanged.connect(self._on_quick_add_item_changed)
        self.quick_add_list.installEventFilter(self)  # For keyboard navigation
        contents_layout.addWidget(self.quick_add_list)

        # Add contents to group box and hide initially
        quick_add_layout.addWidget(self.quick_add_contents)
        self.quick_add_contents.setVisible(False)

        self.quick_add_group.setLayout(quick_add_layout)
        layout.addWidget(self.quick_add_group)

        # Tags table (two columns: Tag and Count)
        layout.addWidget(QLabel("Tags:"))

        # Search and Filter row
        search_layout = QHBoxLayout()

        # Filter button
        self.filter_btn = QPushButton("Filter")
        self.filter_btn.setToolTip("Filter tags using advanced expressions")
        self.filter_btn.clicked.connect(self._open_filter_dialog)
        search_layout.addWidget(self.filter_btn)

        search_layout.addWidget(QLabel("Search:"))

        # Simple search input for fuzzy searching
        self.tag_search_input = QLineEdit()
        self.tag_search_input.setPlaceholderText("Fuzzy search tags...")

        self.tag_search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.tag_search_input, 1)

        layout.addLayout(search_layout)

        self.tags_table = QTableWidget()
        self.tags_table.setColumnCount(3)
        self.tags_table.setHorizontalHeaderLabels(["Category", "Tag", "Count"])

        # Enable multi-row selection for bulk editing
        self.tags_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.tags_table.setSelectionMode(QTableWidget.ExtendedSelection)

        # Make Category and Tag columns editable, Count column read-only
        # Resize columns appropriately
        header = self.tags_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )  # Category column fits content
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Tag column stretches
        header.setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )  # Count column fits content

        # Connect signals
        self.tags_table.itemDoubleClicked.connect(self._edit_tag)
        self.tags_table.installEventFilter(self)  # Install event filter for Del key

        # Enable custom context menu for right-click
        self.tags_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tags_table.customContextMenuRequested.connect(self._show_tags_context_menu)

        layout.addWidget(self.tags_table)

        # Instructions
        instructions = QLabel(
            "• Enter: add tag\n"
            "• Tab/↓: browse suggestions\n"
            "• Double-click: edit tag\n"
            "• Del: delete tag\n"
            "• Quick Add: ↑↓ navigate, Space toggle, Enter/↓ at end = next image"
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(instructions)

    def _update_tag_suggestions(self):
        """Update autocomplete suggestions with all tags in project"""
        # Get only full tags (not categories) for suggestions
        self.all_tags = self.app_manager.get_tag_list().get_all_full_tags()

        # Update widget
        self.tag_entry_widget.set_tags(self.all_tags)

        print(f"[DEBUG] TagWindow: Loaded {len(self.all_tags)} tags")

    def _load_default_filter(self):
        """Load the default filter for tags from the project or library filters

        Note: This only loads a default filter when a project is first opened.
        The active filter (whether default or user-applied) is preserved during
        tag updates unless explicitly cleared by the user.
        """
        # Only load default filter on first load (when _active_filter is empty)
        # This preserves any user-applied filter during the session
        if self._active_filter:
            # User already has a filter applied - preserve it
            return

        # Determine which filters dict to use (project or library)
        if (
            self.app_manager.current_view_mode == "project"
            and self.app_manager.current_project
        ):
            project = self.app_manager.current_project
            filters_dict = project.filters
        else:
            # Library mode
            library = self.app_manager.get_library()
            if not library:
                return
            filters_dict = library.filters

        # Use tag-specific default filter key
        default_filter = filters_dict.get("tag_default_filter", "")
        print(f"[DEBUG] Tag editor loading default filter: {default_filter}")

        if default_filter:
            # Store filter and apply it silently to tags table
            self._active_filter = default_filter
            self._update_visible_tags()
            self._update_filter_button_appearance()
        else:
            # No default filter
            self._active_filter = ""
            self._update_filter_button_appearance()

    def _open_filter_dialog(self):
        """Open filter dialog for tags"""
        from .saved_filters_dialog import SavedFiltersDialog

        # Open dialog in "tags" mode and pass current active filter
        dialog = SavedFiltersDialog(
            self.app_manager,
            parent=self,
            current_filter=self._active_filter,
            mode="tags",
        )

        if dialog.exec_():
            # Get the filter expression from dialog
            filter_expression = dialog.get_filter_expression()

            # Apply filter to tags table
            self._active_filter = filter_expression
            self._update_visible_tags()
            self._update_filter_button_appearance()

    def _update_filter_button_appearance(self):
        """Update filter button appearance based on whether filter is active"""
        if self._active_filter:
            # Filter is active - make button stand out with black text on white background
            self.filter_btn.setStyleSheet(
                "QPushButton { font-weight: bold; background-color: white; color: black; }"
            )
            self.filter_btn.setText("Filter ✓")
        else:
            # No filter active - normal appearance
            self.filter_btn.setStyleSheet("")
            self.filter_btn.setText("Filter")

    def _on_search_changed(self, text: str):
        """Handle search text change - update visible tags"""
        self._update_visible_tags()

    def _on_quick_add_toggled(self, checked: bool):
        """Handle quick add section toggle"""
        # Show/hide the contents
        self.quick_add_contents.setVisible(checked)

        if checked:
            # Parse and populate quick add list when opened
            self._parse_quick_add_tags()

    def _parse_quick_add_tags(self):
        """Parse comma-separated tags/categories and populate quick add list"""
        input_text = self.quick_add_input.text().strip()
        if not input_text:
            self.quick_add_list.clear()
            self.quick_add_tags = []
            return

        # Parse comma-separated values
        entries = [e.strip() for e in input_text.split(",") if e.strip()]

        # Expand categories and collect all tags
        expanded_tags = []
        tag_list = self.app_manager.get_tag_list()

        for entry in entries:
            if ":" in entry:
                # Specific tag (category:value)
                expanded_tags.append(entry)
            else:
                # Category - expand to all tags in that category
                category = entry
                # Get all tags with this category
                all_full_tags = tag_list.get_all_full_tags()
                category_tags = [
                    tag for tag in all_full_tags if tag.startswith(f"{category}:")
                ]
                if category_tags:
                    expanded_tags.extend(category_tags)
                else:
                    # Category doesn't exist yet, but still allow it
                    # User might want to prepare for future tags
                    pass

        # Remove duplicates while preserving order
        seen = set()
        self.quick_add_tags = []
        for tag in expanded_tags:
            if tag not in seen:
                seen.add(tag)
                self.quick_add_tags.append(tag)

        # Populate the list
        self._populate_quick_add_list()

    def _populate_quick_add_list(self):
        """Populate the quick add list with checkboxes"""
        self._updating = True
        self.quick_add_list.clear()

        for tag_str in self.quick_add_tags:
            item = QListWidgetItem(tag_str)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.quick_add_list.addItem(item)

        # Update checkbox states based on active image
        self._update_quick_add_checkboxes()
        self._updating = False

    def _update_quick_add_checkboxes(self):
        """Update checkbox states based on active image tags"""
        if not self.quick_add_tags:
            return

        current_view = self.app_manager.get_current_view()
        if not current_view:
            return

        active_image = current_view.get_active()
        if not active_image:
            return

        # Get tags from active image
        img_data = self.app_manager.load_image_data(active_image)
        image_tag_strs = set(str(tag) for tag in img_data.tags)

        # Update checkboxes
        self._updating = True
        for i in range(self.quick_add_list.count()):
            item = self.quick_add_list.item(i)
            tag_str = item.text()

            if tag_str in image_tag_strs:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
        self._updating = False

    def _on_quick_add_item_changed(self, item: QListWidgetItem):
        """Handle checkbox state change - immediately add/remove tag"""
        if self._updating:
            return

        tag_str = item.text()
        is_checked = item.checkState() == Qt.Checked

        # Parse tag
        parts = tag_str.split(":", 1)
        if len(parts) != 2:
            return

        category = parts[0].strip()
        value = parts[1].strip()

        if not category or not value:
            return

        # Get working images
        current_view = self.app_manager.get_current_view()
        if not current_view:
            return

        working_images = current_view.get_working_images()
        if not working_images:
            return

        # Show multi-select warning if needed
        if len(working_images) > 1 and not self._multi_select_warned:
            if not self._show_multi_select_warning(len(working_images)):
                # User cancelled - revert checkbox state
                self._updating = True
                item.setCheckState(Qt.Unchecked if is_checked else Qt.Checked)
                self._updating = False
                return

        # Add or remove tag from all working images
        for img_path in working_images:
            img_data = self.app_manager.load_image_data(img_path)

            # Check if tag already exists
            existing_tag = None
            for tag in img_data.tags:
                if str(tag) == tag_str:
                    existing_tag = tag
                    break

            if is_checked:
                # Add tag if it doesn't exist
                if not existing_tag:
                    img_data.add_tag(category, value)
                    self.app_manager.save_image_data(img_path, img_data)
            else:
                # Remove tag if it exists
                if existing_tag:
                    img_data.remove_tag(existing_tag)
                    self.app_manager.save_image_data(img_path, img_data)

        # Update the main tags table and suggestions
        self._load_tags()
        self._update_tag_suggestions()
        self.app_manager.update_project(save=True)

    def _show_multi_select_warning(self, count: int) -> bool:
        """Show warning that multiple images are selected

        Returns:
            True if user clicks OK to continue, False if user cancels
        """
        reply = QMessageBox.warning(
            self,
            "⚠ Multiple Images Selected",
            f"{count} images are selected.\n\n"
            f"This operation will modify tags on ALL selected images.\n\n"
            f"Press Enter to confirm, or click Cancel to cancel.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,  # Make Cancel the default so ESC cancels
        )

        if reply == QMessageBox.StandardButton.Ok:
            return True
        else:
            return False

    def _update_visible_tags(self):
        """Update visible tags using two-stage filtering: filter parser then fuzzy search

        Stage 1: Apply active filter (if any) using filter parser
        Stage 2: Apply fuzzy search from search input on category and tag columns
        """
        # Collect all tag data from table (category, tag, full_tag)
        all_table_tags = []
        for row in range(self.tags_table.rowCount()):
            category_item = self.tags_table.item(row, 0)
            tag_item = self.tags_table.item(row, 1)
            if category_item and tag_item:
                category = category_item.text()
                tag_value = tag_item.text()
                full_tag = f"{category}:{tag_value}"
                all_table_tags.append((row, category, tag_value, full_tag))

        # Stage 1: Apply filter parser if active filter is set
        if self._active_filter:
            filtered_tags = []
            for row, category, tag_value, full_tag in all_table_tags:
                try:
                    # Evaluate filter with single tag
                    result = evaluate_filter(self._active_filter, [full_tag])
                    if result:
                        filtered_tags.append((row, category, tag_value, full_tag))
                except ValueError:
                    # Invalid filter - hide this tag
                    pass
        else:
            # No filter active - include all tags
            filtered_tags = all_table_tags

        # Stage 2: Apply fuzzy search
        search_text = self.tag_search_input.text().strip()

        if search_text:
            # Search in category, tag, and full tag
            matching_rows = set()

            for row, category, tag_value, full_tag in filtered_tags:
                # Search in category
                if fuzzy_search(search_text, [category]):
                    matching_rows.add(row)
                    continue

                # Search in tag value
                if fuzzy_search(search_text, [tag_value]):
                    matching_rows.add(row)
                    continue

                # Search in full tag
                if fuzzy_search(search_text, [full_tag]):
                    matching_rows.add(row)
                    continue

            # Create final visible set
            visible_tags = [
                (row, category, tag_value, full_tag)
                for row, category, tag_value, full_tag in filtered_tags
                if row in matching_rows
            ]
        else:
            # No search text - show all filtered tags
            visible_tags = filtered_tags

        # Update table visibility
        visible_rows = {row for row, _, _, _ in visible_tags}
        for row in range(self.tags_table.rowCount()):
            self.tags_table.setRowHidden(row, row not in visible_rows)

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

        # Cache image data to avoid repeated loading (performance optimization)
        image_data_cache = {}
        for img_path in working_images:
            image_data_cache[img_path] = self.app_manager.load_image_data(img_path)

        # Track tag occurrences efficiently
        tag_occurrences = {}  # tag_str -> list of (tag_object, img_path)

        for img_path, img_data in image_data_cache.items():
            for tag in img_data.tags:
                tag_str = str(tag)
                if tag_str not in tag_occurrences:
                    tag_occurrences[tag_str] = []
                tag_occurrences[tag_str].append((tag, img_path))

        # Populate table based on number of images
        if len(working_images) == 1:
            # Single image: show ALL tags including duplicates
            img_data = image_data_cache[working_images[0]]
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
                self._add_tag_row(tag.category, tag.value, count_text, tag, idx)
        else:
            # Multiple images: show unique tags with counts
            for tag_str, occurrences in sorted(tag_occurrences.items()):
                tag = occurrences[0][0]  # Use first occurrence as representative
                count = len(occurrences)

                # Count total occurrences across all selected images (including duplicates within images)
                # Use cached data for performance
                total_count = 0
                for _, img_path in occurrences:
                    img_data = image_data_cache[img_path]
                    total_count += sum(1 for t in img_data.tags if str(t) == tag_str)

                # Build count text
                if total_count > count:
                    num_dups = total_count - count
                    dup_word = "duplicate" if num_dups == 1 else "duplicates"
                    count_text = f"{total_count}, {num_dups} {dup_word}"
                else:
                    count_text = str(count)

                # Add row to table
                self._add_tag_row(tag.category, tag.value, count_text, tag, count)

        # Don't clear search input - preserve user's search when reloading tags
        # self.tag_search_input.clear()  # Commented out to preserve search

        # Update visible tags based on active filter and current search
        self._update_visible_tags()

        # Update quick add checkboxes if quick add is active
        if self.quick_add_group.isChecked():
            self._update_quick_add_checkboxes()

        self._updating = False

    def _add_tag_row(
        self, category_str: str, tag_str: str, count_text: str, tag_obj, user_data
    ):
        """Add a row to the tags table"""
        row = self.tags_table.rowCount()
        self.tags_table.insertRow(row)

        # Category column (editable)
        category_item = QTableWidgetItem(category_str)
        category_item.setData(Qt.UserRole, tag_obj)
        category_item.setData(Qt.UserRole + 1, user_data)
        self.tags_table.setItem(row, 0, category_item)

        # Tag column (editable)
        tag_item = QTableWidgetItem(tag_str)
        tag_item.setData(Qt.UserRole, tag_obj)
        tag_item.setData(Qt.UserRole + 1, user_data)
        self.tags_table.setItem(row, 1, tag_item)

        # Count column (read-only)
        count_item = QTableWidgetItem(count_text)
        count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)  # Make read-only
        self.tags_table.setItem(row, 2, count_item)

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
            self._add_tag_row(tag.category, tag.value, count_text, tag, count)

    def _add_tag(self, category: str, value: str):
        """Add new tag to selected images"""
        if not category or not value:
            return

        # Add tag to all working images (only if not already present)
        current_view = self.app_manager.get_current_view()
        working_images = current_view.get_working_images() if current_view else []

        # Show multi-select warning EVERY TIME for multiple images
        if len(working_images) > 1:
            if not self._show_multi_select_warning(len(working_images)):
                # User cancelled
                return

        for img_path in working_images:
            img_data = self.app_manager.load_image_data(img_path)

            # Check if tag already exists (case-sensitive comparison)
            tag_str = f"{category}:{value}"
            tag_exists = any(str(tag) == tag_str for tag in img_data.tags)

            # Only add if tag doesn't exist
            if not tag_exists:
                img_data.add_tag(category, value)
                self.app_manager.save_image_data(img_path, img_data)

        # Clear inputs in widget (respecting keep_category mode)
        self.tag_entry_widget.cleanup_after_add()

        self._load_tags()
        self._update_tag_suggestions()
        self.app_manager.update_project(save=True)

    def _edit_tag(self, item: QTableWidgetItem):
        """Edit an existing tag"""
        if not item:
            return

        # Allow editing category (column 0) or tag (column 1) columns
        if item.column() not in [0, 1]:
            return

        old_tag = item.data(Qt.UserRole)
        if not old_tag:
            return

        # Store the current selection before any changes
        # This handles the case where double-click clears multi-selection
        self._stored_selection = set()
        for selected_item in self.tags_table.selectedItems():
            self._stored_selection.add(selected_item.row())

        # If no explicit selection, at least include the clicked row
        if not self._stored_selection:
            self._stored_selection.add(item.row())

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

        # Only process changes to category (column 0) or tag (column 1) columns
        if item.column() not in [0, 1]:
            return

        new_text = item.text().strip()
        current_view = self.app_manager.get_current_view()
        working_images = current_view.get_working_images() if current_view else []

        # Get selected rows for multi-select editing
        # Use stored selection from when editing started (handles double-click clearing selection)
        selected_rows = getattr(self, "_stored_selection", set())

        # If no stored selection, fall back to current selection
        if not selected_rows:
            selected_rows = set()
            for selected_item in self.tags_table.selectedItems():
                selected_rows.add(selected_item.row())

        # If still no selection, use the clicked row
        if not selected_rows:
            selected_rows = {item.row()}
        # If only one row is selected and it's the clicked row, that's fine
        # If multiple rows are selected, use all of them

        # Show multi-select warning EVERY TIME if editing multiple images OR multiple tags
        multi_edit_warning = len(working_images) > 1 or len(selected_rows) > 1
        if multi_edit_warning:
            count = max(len(selected_rows), len(working_images))
            if not self._show_multi_select_warning(count):
                # User cancelled - revert the edited item
                if item.column() == 0:  # Category column
                    item.setText(old_tag.category)
                else:  # Tag column
                    item.setText(old_tag.value)
                return

        # Process each selected row
        for row in selected_rows:
            # Get the tag data for this row
            category_item = self.tags_table.item(row, 0)
            tag_item = self.tags_table.item(row, 1)

            if not category_item or not tag_item:
                continue

            # Get the old tag for this row
            row_old_tag = category_item.data(Qt.UserRole)
            if not row_old_tag:
                continue

            # Determine the new category and value based on what was edited
            if item.column() == 0:  # Editing category
                new_category = new_text
                new_value = tag_item.text().strip()
            else:  # Editing tag value
                new_category = category_item.text().strip()
                new_value = new_text

            if not new_category or not new_value:
                # Delete tag from all images
                for img_path in working_images:
                    img_data = self.app_manager.load_image_data(img_path)
                    if row_old_tag in img_data.tags:
                        img_data.remove_tag(row_old_tag)
                        self.app_manager.save_image_data(img_path, img_data)
            else:
                # Update tag in all images
                for img_path in working_images:
                    img_data = self.app_manager.load_image_data(img_path)
                    # Remove old tag and add new tag
                    if row_old_tag in img_data.tags:
                        idx = img_data.tags.index(row_old_tag)
                        img_data.tags[idx] = Tag(new_category, new_value)
                        self.app_manager.save_image_data(img_path, img_data)

        # Rebuild tag list from all images to reflect changes
        self.app_manager.rebuild_tag_list()

        # Preserve current search text before reloading
        current_search = self.tag_search_input.text().strip()

        # Reload tags
        self._load_tags()

        # Restore search text and update suggestions
        if current_search:
            self.tag_search_input.setText(current_search)
        # If no search was active, leave search box empty
        self._update_tag_suggestions()
        self.app_manager.update_project(save=True)

    def _delete_tag(self):
        """Delete all selected tags from all working images"""
        # Get all selected rows (not just currentRow)
        selected_rows = set()
        for item in self.tags_table.selectedItems():
            selected_rows.add(item.row())

        if not selected_rows:
            return

        # Collect all tags to delete from selected rows
        tags_to_delete = []
        for row in selected_rows:
            tag_item = self.tags_table.item(row, 0)
            if tag_item:
                tag_to_delete = tag_item.data(Qt.UserRole)
                if tag_to_delete:
                    tags_to_delete.append(tag_to_delete)

        if not tags_to_delete:
            return

        current_view = self.app_manager.get_current_view()
        working_images = current_view.get_working_images() if current_view else []

        # Show multi-select warning EVERY TIME for multiple images
        if len(working_images) > 1:
            if not self._show_multi_select_warning(len(working_images)):
                # User cancelled - don't delete tags
                return

        # Delete all selected tags from all images
        for img_path in working_images:
            img_data = self.app_manager.load_image_data(img_path)
            for tag_to_delete in tags_to_delete:
                if tag_to_delete in img_data.tags:
                    img_data.remove_tag(tag_to_delete)
            self.app_manager.save_image_data(img_path, img_data)

        # Rebuild tag list from all images to reflect deletions
        self.app_manager.rebuild_tag_list()

        # Reload tags
        self._load_tags()
        self._update_tag_suggestions()
        self.app_manager.update_project(save=True)

    def _show_tags_context_menu(self, position):
        """Show context menu for tags table on right-click"""
        # Get selected rows
        selected_rows = set()
        for item in self.tags_table.selectedItems():
            selected_rows.add(item.row())

        if not selected_rows:
            return  # No selection

        # Get full tag strings (category:value) from selected rows
        selected_tags = []
        for row in selected_rows:
            category_item = self.tags_table.item(row, 0)  # Category column
            tag_item = self.tags_table.item(row, 1)  # Tag column
            if category_item and tag_item:
                category = category_item.text().strip()
                tag_value = tag_item.text().strip()
                if category and tag_value:
                    full_tag = f"{category}:{tag_value}"
                    selected_tags.append(full_tag)

        if not selected_tags:
            return

        # Create context menu
        menu = QMenu(self)

        # Add "Edit Category" action for batch editing
        edit_category_action = QAction("Edit Category (Batch)", self)
        edit_category_action.setToolTip("Edit category for all selected tags")
        edit_category_action.triggered.connect(
            lambda: self._batch_edit_column(list(selected_rows), 0)
        )
        menu.addAction(edit_category_action)

        # Add "Edit Tag" action for batch editing
        edit_tag_action = QAction("Edit Tag (Batch)", self)
        edit_tag_action.setToolTip("Edit tag value for all selected tags")
        edit_tag_action.triggered.connect(
            lambda: self._batch_edit_column(list(selected_rows), 1)
        )
        menu.addAction(edit_tag_action)

        menu.addSeparator()

        # Add "Add to Gallery Filter" action
        filter_action = QAction("Add to Gallery Filter", self)
        filter_action.setToolTip("Add selected tags to gallery filter as OR conditions")
        filter_action.triggered.connect(
            lambda: self._add_tags_to_gallery_filter(selected_tags)
        )
        menu.addAction(filter_action)

        # Show menu at cursor position
        menu.exec_(self.tags_table.viewport().mapToGlobal(position))

    def _batch_edit_column(self, selected_rows: List[int], column: int):
        """Batch edit category (column 0) or tag (column 1) for multiple selected rows

        Args:
            selected_rows: List of row indices to edit
            column: 0 for category, 1 for tag value
        """
        if not selected_rows:
            return

        # Get column name for display
        column_name = "Category" if column == 0 else "Tag"

        # Collect unique values from selected rows to show in dialog
        current_values = set()
        row_data = []  # Store (row, category, tag) for later processing

        for row in selected_rows:
            category_item = self.tags_table.item(row, 0)
            tag_item = self.tags_table.item(row, 1)

            if category_item and tag_item:
                category = category_item.text().strip()
                tag_value = tag_item.text().strip()
                row_data.append((row, category, tag_value))

                if column == 0:
                    current_values.add(category)
                else:
                    current_values.add(tag_value)

        if not row_data:
            return

        # Build preview text
        preview_lines = []
        for row, category, tag_value in row_data:
            if column == 0:
                preview_lines.append(f"{category} → [new value]")
            else:
                preview_lines.append(f"{category}:{tag_value} → {category}:[new value]")

        # Create batch edit dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Batch Edit {column_name}")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(300)

        layout = QVBoxLayout(dialog)

        # Info label
        info_text = f"Editing {column_name.lower()} for {len(row_data)} tag{'s' if len(row_data) != 1 else ''}"
        if len(current_values) == 1:
            current_val = list(current_values)[0]
            info_text += f"\nCurrent {column_name.lower()}: {current_val}"
        else:
            info_text += f"\nCurrent values: {', '.join(sorted(current_values))}"

        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(info_label)

        # Input field for new value
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel(f"New {column_name.lower()}:"))
        new_value_input = QLineEdit()
        new_value_input.setPlaceholderText(f"Enter new {column_name.lower()}")
        input_layout.addWidget(new_value_input)
        layout.addLayout(input_layout)

        # Preview section
        layout.addWidget(QLabel("Preview of changes:"))

        preview_text = QTextEdit()
        preview_text.setReadOnly(True)
        preview_text.setMaximumHeight(150)
        preview_text.setPlainText("\n".join(preview_lines[:10]))
        if len(preview_lines) > 10:
            preview_text.insertPlainText(f"\n... and {len(preview_lines) - 10} more")
        layout.addWidget(preview_text)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply Changes")
        apply_btn.clicked.connect(dialog.accept)
        apply_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        apply_btn.setDefault(True)  # Make Apply the default button (triggered by Enter)
        button_layout.addWidget(apply_btn)

        layout.addLayout(button_layout)

        # Show dialog and wait for result
        result = dialog.exec_()
        print(f"\n[BATCH_EDIT_DEBUG] Dialog exec() returned: {result}")
        print(f"[BATCH_EDIT_DEBUG] Checking if result == 1: {result == 1}")

        if result != 1:  # QDialog.Accepted is 1
            print(f"[BATCH_EDIT_DEBUG] Dialog not accepted, returning early")
            return

        new_value = new_value_input.text().strip()
        print(f"[BATCH_EDIT_DEBUG] Got new value: '{new_value}'")

        if not new_value:
            print(
                f"[BATCH_EDIT_DEBUG] New value is empty, showing warning and returning"
            )
            QMessageBox.warning(
                self, "Empty Value", f"Please enter a new {column_name.lower()}."
            )
            return

        # Apply changes to all selected rows
        current_view = self.app_manager.get_current_view()
        working_images = current_view.get_working_images() if current_view else []

        # Show multi-select warning if needed
        if len(working_images) > 1 and not self._multi_select_warned:
            if not self._show_multi_select_warning(len(working_images)):
                return

        # Process each selected row
        print(
            f"[DEBUG] Starting batch edit: {len(row_data)} rows, column={column}, new_value='{new_value}'"
        )
        print(f"[DEBUG] Working images count: {len(working_images)}")

        tags_updated_count = 0

        for row, old_category, old_tag_value in row_data:
            # Get the tag object
            category_item = self.tags_table.item(row, 0)
            old_tag = category_item.data(Qt.UserRole) if category_item else None

            print(
                f"[DEBUG] Processing row {row}: category='{old_category}', tag='{old_tag_value}', old_tag={old_tag}"
            )

            if not old_tag:
                print(f"[DEBUG] No tag object found, skipping row {row}")
                continue

            # Determine new category and value
            if column == 0:  # Editing category
                new_category = new_value
                new_tag_value = old_tag_value
            else:  # Editing tag value
                new_category = old_category
                new_tag_value = new_value

            print(f"[DEBUG] New tag: {new_category}:{new_tag_value}")

            # Update tag in all working images
            for img_path in working_images:
                img_data = self.app_manager.load_image_data(img_path)

                # Find and replace the tag
                if old_tag in img_data.tags:
                    idx = img_data.tags.index(old_tag)
                    from .data_models import Tag

                    img_data.tags[idx] = Tag(new_category, new_tag_value)
                    self.app_manager.save_image_data(img_path, img_data)
                    tags_updated_count += 1
                    print(f"[DEBUG] Updated tag in {img_path}")
                else:
                    print(f"[DEBUG] Old tag {old_tag} not found in {img_path}")

        # Rebuild tag list and reload
        self.app_manager.rebuild_tag_list()
        self._load_tags()
        self._update_tag_suggestions()
        self.app_manager.update_project(save=True)

        QMessageBox.information(
            self,
            "Batch Edit Complete",
            f"Updated {column_name.lower()} for {len(row_data)} tag{'s' if len(row_data) != 1 else ''}.",
        )

    def _add_tags_to_gallery_filter(self, selected_tags: List[str]):
        """Add selected tags to the gallery filter as OR conditions"""
        if not selected_tags:
            return

        # Get current filter expression
        current_filter = self.app_manager.current_filter_expression or ""

        # Create OR expression from selected tags, wrapping tags with spaces in quotes
        def format_tag(tag: str) -> str:
            """Format a tag, wrapping in quotes if it contains spaces"""
            if " " in tag:
                return f'"{tag}"'
            return tag

        formatted_tags = [format_tag(tag) for tag in selected_tags]

        if len(formatted_tags) == 1:
            tag_expression = formatted_tags[0]
        else:
            tag_expression = " OR ".join(formatted_tags)

        # Combine with existing filter
        if current_filter.strip():
            # Append with AND to existing filter
            new_filter = f"({current_filter}) AND ({tag_expression})"
        else:
            # No existing filter, use tag expression directly
            new_filter = tag_expression

        # Apply the new filter
        from .saved_filters_dialog import SavedFiltersDialog
        from .filter_parser import evaluate_filter

        image_list = self.app_manager.get_image_list()
        if not image_list:
            return

        # Filter images
        all_images = image_list.get_all_paths()
        filtered = []

        for img_path in all_images:
            try:
                img_data = self.app_manager.load_image_data(img_path)
                img_tag_strs = [str(tag) for tag in img_data.tags]
                result = evaluate_filter(new_filter, img_tag_strs)

                if result:
                    filtered.append(img_path)
            except Exception as e:
                print(f"ERROR: Error filtering image {img_path}: {e}")
                continue

        # Create filtered view (always create, even if empty)
        from .data_models import ImageList

        base_dir = image_list._base_dir
        if base_dir:
            filtered_view = ImageList.create_filtered(base_dir, filtered)
            self.app_manager.set_filtered_view(filtered_view)
            self.app_manager.current_filter_expression = new_filter
            print(f"[DEBUG] Added tags to gallery filter: {len(filtered)} images match")

        # Update gallery filter button appearance
        # This will be handled by the gallery's signal connections

    def eventFilter(self, obj, event):
        """Handle keyboard events for inline suggestion navigation and tag deletion"""
        # Check if widgets exist (may be called during initialization)
        if not hasattr(self, "tags_table"):
            return super().eventFilter(obj, event)

        if obj == self.quick_add_list and event.type() == QEvent.KeyPress:
            # Handle keyboard navigation in quick add list
            key = event.key()

            if key == Qt.Key_Space:
                # Toggle checkbox on current item
                current_item = self.quick_add_list.currentItem()
                if current_item:
                    # Toggle the check state
                    new_state = (
                        Qt.Unchecked
                        if current_item.checkState() == Qt.Checked
                        else Qt.Checked
                    )
                    current_item.setCheckState(new_state)
                    return True

            elif key == Qt.Key_Return or key == Qt.Key_Enter:
                # Move to next image
                self._change_active_image(1)
                # Reset multi-select warning for next image
                self._multi_select_warned = False
                return True

            elif key == Qt.Key_Down:
                # Navigate down in list with wrap-around
                current_row = self.quick_add_list.currentRow()
                if current_row == self.quick_add_list.count() - 1:
                    # At bottom, wrap to top
                    self.quick_add_list.setCurrentRow(0)
                else:
                    # Move down
                    self.quick_add_list.setCurrentRow(current_row + 1)
                return True

            elif key == Qt.Key_Up:
                # Navigate up in list with wrap-around
                current_row = self.quick_add_list.currentRow()
                if current_row == 0:
                    # At top, wrap to bottom
                    self.quick_add_list.setCurrentRow(self.quick_add_list.count() - 1)
                else:
                    # Move up
                    self.quick_add_list.setCurrentRow(current_row - 1)
                return True

            elif key == Qt.Key_Left:
                # Navigate to previous image
                self._change_active_image(-1)
                # Reset multi-select warning for new image
                self._multi_select_warned = False
                return True

            elif key == Qt.Key_Right:
                # Navigate to next image
                self._change_active_image(1)
                # Reset multi-select warning for new image
                self._multi_select_warned = False
                return True

        elif obj == self.tags_table and event.type() == QEvent.KeyPress:
            # Handle Del key on tags table
            if event.key() == Qt.Key_Delete:
                self._delete_tag()
                return True

        return super().eventFilter(obj, event)

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

    def keyPressEvent(self, event):
        """Handle keyboard events at window level"""
        super().keyPressEvent(event)

    def _change_active_image(self, direction: int):
        """Change the active image in the gallery - works on current view (filtered or full)"""
        current_view = self.app_manager.get_current_view()
        main_image_list = self.app_manager.get_image_list()

        if not current_view or not main_image_list:
            return

        all_images = current_view.get_all_paths()
        active_image = current_view.get_active()

        if not all_images or not active_image:
            return

        try:
            current_idx = all_images.index(active_image)
            new_idx = (current_idx + direction) % len(all_images)  # Wrap around

            new_active = all_images[new_idx]

            # Set active on current view (for filtered navigation)
            current_view.set_active(new_active)
            # Also set on main image list to ensure signals work
            if main_image_list != current_view:
                main_image_list.set_active(new_active)

            # Directly update gallery selection
            from .gallery import Gallery

            current_widget = self.parent()
            gallery = None

            while current_widget:
                if hasattr(current_widget, "findChildren"):
                    galleries = current_widget.findChildren(Gallery)
                    if galleries:
                        gallery = galleries[0]
                        break
                current_widget = current_widget.parent()

            if gallery and hasattr(gallery, "_on_active_image_changed"):
                gallery._on_active_image_changed()

        except (ValueError, IndexError):
            pass

    def showEvent(self, event):
        """Update when window is shown"""
        super().showEvent(event)
        self._update_tag_suggestions()
        self._load_tags()
