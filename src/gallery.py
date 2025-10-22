"""
Gallery - Grid/List view of project images with thumbnails and selection
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QPushButton, QSlider, QCheckBox, QMessageBox, QScrollArea, QComboBox
)
from PyQt5.QtCore import Qt, QSize, QTimer, QEvent
from PyQt5.QtGui import QPixmap, QIcon, QPixmapCache
from pathlib import Path


class GalleryTreeItemWidget(QWidget):
    """Custom widget for gallery tree items with thumbnail, checkbox, and text info"""

    def __init__(self, image_path: Path, image_name: str, caption: str, thumbnail_size: int,
                 lazy_load: bool = False, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.image_name = image_name
        self.caption = caption
        self.thumbnail_size = thumbnail_size
        self.thumbnail_loaded = False
        self.setup_ui(lazy_load)

    def setup_ui(self, lazy_load: bool):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        # 1st: Checkbox
        self.checkbox = QCheckBox()
        # Add outline only to the indicator to make checkbox visible on dark themes
        self.checkbox.setStyleSheet("""
            QCheckBox {
                background: transparent;
                padding: 0px;
                margin: 0px;
            }
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
                border: 1px solid palette(text);
                border-radius: 2px;
                background: transparent;
            }
            QCheckBox::indicator:checked {
                background: palette(text);
                border: 1px solid palette(text);
            }
            QCheckBox::indicator:checked::image {
                image: none;
            }
        """)
        layout.addWidget(self.checkbox)

        # 2nd: Thumbnail (full row height)
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(self.thumbnail_size, self.thumbnail_size)
        self.thumbnail_label.setStyleSheet("border: none;")  # Remove borders

        if not lazy_load:
            # Load immediately (legacy behavior)
            self._load_thumbnail()
        else:
            # Placeholder for lazy loading
            self.thumbnail_label.setText("...")
            self.thumbnail_label.setStyleSheet("border: none; background-color: transparent;")

        layout.addWidget(self.thumbnail_label)

        # 3rd: Text display area with rows for filename and caption
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(5, 0, 0, 0)
        text_layout.setSpacing(1)

        # Filename row
        self.name_label = QLabel(self.image_name)
        self.name_label.setStyleSheet("font-size: 12pt; font-weight: bold; color: palette(text);")
        self.name_label.setWordWrap(True)
        text_layout.addWidget(self.name_label)

        # Caption row
        self.caption_label = QLabel(self.caption if self.caption else "(no caption)")
        self.caption_label.setStyleSheet("font-size: 12pt; color: palette(text);")
        self.caption_label.setWordWrap(True)
        text_layout.addWidget(self.caption_label)

        layout.addLayout(text_layout)
        layout.addStretch()

    def _load_thumbnail(self):
        """Load thumbnail from cache or disk"""
        if self.thumbnail_loaded:
            return

        # Try to load from cache first
        cache_key = f"{self.image_path}_{self.thumbnail_size}"
        pixmap = QPixmapCache.find(cache_key)

        if pixmap is None:
            # Not in cache - load from disk and scale
            pixmap = QPixmap(str(self.image_path))
            if not pixmap.isNull():
                # Scale to fit within the fixed size while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(self.thumbnail_size, self.thumbnail_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                # Cache the scaled thumbnail for future use
                QPixmapCache.insert(cache_key, scaled_pixmap)
                self.thumbnail_label.setPixmap(scaled_pixmap)
                # Center the pixmap in the fixed-size label
                self.thumbnail_label.setAlignment(Qt.AlignCenter)
            else:
                self.thumbnail_label.setText("No Image")
                self.thumbnail_label.setAlignment(Qt.AlignCenter)
        else:
            # Found in cache - use it directly
            self.thumbnail_label.setPixmap(pixmap)
            self.thumbnail_label.setAlignment(Qt.AlignCenter)

        self.thumbnail_loaded = True

    def load_thumbnail_if_needed(self):
        """Public method to trigger lazy loading"""
        if not self.thumbnail_loaded:
            self._load_thumbnail()


# Backward compatibility
GalleryItemWidget = GalleryTreeItemWidget


class Gallery(QWidget):
    """Gallery widget - shows list of images with thumbnails and selection"""

    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self._updating = False
        self._last_filtered_images = None

        self.setWindowTitle("Gallery")
        self.setMinimumSize(300, 200)
        self.resize(500, 700)  # Default size, but can be resized smaller

        # Configure pixmap cache size (in KB) - 100MB for thumbnail caching
        # This allows ~1000 thumbnails at 100KB each to be cached
        QPixmapCache.setCacheLimit(102400)  # 100MB in KB

        # Timer for debouncing thumbnail resize
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._apply_resize)

        # Lazy loading support
        self._lazy_load_enabled = True
        self._pending_thumbnail_indices = []  # List of indices that need thumbnail loading
        self._lazy_load_timer = QTimer()
        self._lazy_load_timer.timeout.connect(self._load_next_batch)
        self._lazy_load_batch_size = 10  # Load 10 thumbnails per timer tick

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
        # Note: Only connect _on_selection_changed, which has smart logic to refresh only when needed
        # Do NOT connect refresh() directly - it would rebuild the entire gallery on every click!
        self.app_manager.project_changed.connect(self._on_selection_changed)
        self.app_manager.library_changed.connect(self._on_selection_changed)

        # Initial load
        self.refresh()
        self._update_source_selector()

    @property
    def image_list(self):
        """Compatibility object to redirect QListWidget calls to QTreeWidget"""
        return self

    # QListWidget compatibility methods
    def count(self):
        return self.image_tree.topLevelItemCount()

    def clear(self):
        self.image_tree.clear()

    def item(self, index):
        return self.image_tree.topLevelItem(index)

    def itemWidget(self, item):
        return self.image_tree.itemWidget(item, 0)

    def setCurrentRow(self, row):
        item = self.image_tree.topLevelItem(row)
        if item:
            self.image_tree.setCurrentItem(item)

    def currentRow(self):
        item = self.image_tree.currentItem()
        if item:
            for i in range(self.image_tree.topLevelItemCount()):
                if self.image_tree.topLevelItem(i) == item:
                    return i
        return -1

    def takeItem(self, row):
        item = self.image_tree.takeTopLevelItem(row)
        return item

    def addItem(self, item):
        # This should not be used with the new tree structure
        pass

    def setItemWidget(self, item, widget):
        self.image_tree.setItemWidget(item, 0, widget)

    def viewport(self):
        return self.image_tree.viewport()

    def visualItemRect(self, item):
        return self.image_tree.visualItemRect(item)

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Info label
        self.info_label = QLabel("Gallery - Select images")
        layout.addWidget(self.info_label)

        # Controls row above tree
        controls_row0 = QHBoxLayout()

        # Source selector dropdown
        controls_row0.addWidget(QLabel("Show related images from:"))
        self.source_combo = QComboBox()
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        controls_row0.addWidget(self.source_combo)

        controls_row0.addStretch()
        layout.addLayout(controls_row0)

        # Tree widget
        self.image_tree = QTreeWidget()
        self.image_tree.setHeaderHidden(True)  # Hide column labels
        self.image_tree.setColumnCount(1)      # Only use first column for content
        self.image_tree.setColumnWidth(0, 600)  # Make main column wider
        self.image_tree.currentItemChanged.connect(self._on_item_changed)
        self.image_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.image_tree.itemExpanded.connect(self._on_item_expanded)
        self.image_tree.itemCollapsed.connect(self._on_item_collapsed)
        # Connect scrollbar to trigger lazy loading of newly visible items
        self.image_tree.verticalScrollBar().valueChanged.connect(self._on_scroll)
        # Install event filter to handle keyboard events
        self.image_tree.installEventFilter(self)

        # Make tree arrows bigger using indentation and icon size
        self.image_tree.setIndentation(30)  # Double the default indentation (default is ~20)
        self.image_tree.setIconSize(QSize(20, 20))  # Make icons much bigger
        self.image_tree.setExpandsOnDoubleClick(False)  # We'll handle double click ourselves
        self.image_tree.setRootIsDecorated(True)  # Show tree arrows for items with children

        layout.addWidget(self.image_tree)

        # Bottom controls - Row 1: Selection buttons
        controls_row1 = QHBoxLayout()

        # Selection buttons
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        controls_row1.addWidget(select_all_btn)

        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.clicked.connect(self._remove_all)
        controls_row1.addWidget(clear_all_btn)

        controls_row1.addStretch()

        # Size slider
        controls_row1.addWidget(QLabel("Size:"))
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setMinimum(50)
        self.size_slider.setMaximum(300)
        self.size_slider.setValue(self.app_manager.get_config().thumbnail_size)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        self.size_slider.setMaximumWidth(150)
        controls_row1.addWidget(self.size_slider)

        layout.addLayout(controls_row1)

        # Bottom controls - Row 2: Action buttons
        controls_row2 = QHBoxLayout()

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._delete_images)
        remove_btn.setToolTip("Remove selected images from project (keeps files)")
        controls_row2.addWidget(remove_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_images_and_files)
        delete_btn.setToolTip("Delete selected images from project AND filesystem")
        delete_btn.setStyleSheet("QPushButton { background-color: #d32f2f; color: white; }")
        controls_row2.addWidget(delete_btn)

        copy_btn = QPushButton("Copy Paths")
        copy_btn.clicked.connect(self._copy_image_paths)
        copy_btn.setToolTip("Copy selected image paths to clipboard")
        controls_row2.addWidget(copy_btn)

        controls_row2.addStretch()

        layout.addLayout(controls_row2)

        # Keyboard hints
        keyboard_hint = QLabel("Keyboard: ↑↓ navigate • Space toggle select • C clear all • Del remove")
        keyboard_hint.setStyleSheet("color: gray; font-size: 9px;")
        keyboard_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(keyboard_hint)

    def refresh(self):
        """Refresh list from current view (project or library)"""
        if self._updating:
            return

        self._updating = True

        # Stop any pending lazy loading
        self._lazy_load_timer.stop()
        self._pending_thumbnail_indices.clear()

        current_view = self.app_manager.get_current_view()

        # Clear tree
        self.image_tree.clear()

        if current_view is None:
            self.info_label.setText("No library or project loaded")
            self._updating = False
            return

        # Get images from current view (filtered or all)
        images = current_view.get_all_paths()
        self._last_filtered_images = tuple(images)

        self.info_label.setText(f"Gallery: {len(images)} images")

        # Update source selector
        self._update_source_selector()

        # Build basic tree structure
        self._build_tree(images)

        # Set initial active image if none set
        if images and current_view.get_active() is None:
            current_view.set_active(images[0])

        self._updating = False

        # Start lazy loading thumbnails if enabled
        if self._lazy_load_enabled:
            self._start_lazy_loading()

    def _on_row_changed(self, current_row):
        """Handle row selection change - set as active image"""
        if self._updating or current_row < 0:
            return

        item = self.image_list.item(current_row)
        if item:
            img_path = item.data(0, Qt.UserRole)
            if img_path:
                current_view = self.app_manager.get_current_view()
                if current_view is not None:
                    current_view.set_active(img_path)
                    self.app_manager.update_project(save=False)

    def _on_checkbox_changed(self, image_path: Path, state: int):
        """Handle checkbox state change"""
        if self._updating:
            return

        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        if state == Qt.Checked:
            current_view.select(image_path)
        else:
            current_view.deselect(image_path)

        self.app_manager.update_project(save=False)

    def _select_all(self):
        """Select all images in current list"""
        current_view = self.app_manager.get_current_view()
        if current_view is not None:
            current_view.select_all()
            self.app_manager.update_project(save=False)

    def _remove_all(self):
        """Clear all selections"""
        current_view = self.app_manager.get_current_view()
        if current_view is not None:
            current_view.clear_selection()
            self.app_manager.update_project(save=False)

    def _on_size_changed(self, value: int):
        """Handle thumbnail size change - debounced"""
        # Update config
        self.app_manager.get_config().thumbnail_size = value
        self.app_manager.update_config()
        # Debounce the refresh - only apply after user stops dragging
        self.resize_timer.stop()
        self.resize_timer.start(150)  # 150ms delay

    def _apply_resize(self):
        """Apply thumbnail resize after debounce delay"""
        self.refresh()

    def _start_lazy_loading(self):
        """Start lazy loading thumbnails - prioritize visible items first"""
        if not self._lazy_load_enabled:
            return

        # Get visible items immediately
        visible_items = self._get_visible_items()

        # Load visible items immediately
        for item in visible_items:
            if not item.isDisabled():  # Skip disabled items like category headers
                widget = self.image_tree.itemWidget(item, 0)
                if widget and hasattr(widget, 'load_thumbnail_if_needed'):
                    widget.load_thumbnail_if_needed()

        # Queue all top-level items for background loading (children will be loaded when visible)
        self._pending_thumbnail_indices = list(range(self.image_tree.topLevelItemCount()))

        # Start background loading timer if there are pending items
        if self._pending_thumbnail_indices:
            self._lazy_load_timer.start(10)  # 10ms interval for smooth loading

    def _get_visible_items(self):
        """Get all visible items in the tree (including children)"""
        visible_items = []

        # Get the viewport rect
        viewport_rect = self.image_tree.viewport().rect()

        # Check all top-level items and their children
        for i in range(self.image_tree.topLevelItemCount()):
            top_item = self.image_tree.topLevelItem(i)
            top_rect = self.image_tree.visualItemRect(top_item)

            # Check if top item is visible
            if viewport_rect.intersects(top_rect):
                visible_items.append(top_item)

            # Always check children if parent exists (even if not expanded yet)
            # This ensures thumbnails are pre-loaded when items become visible
            for j in range(top_item.childCount()):
                child_item = top_item.child(j)
                child_rect = self.image_tree.visualItemRect(child_item)

                # Check if child is visible or parent is expanded
                if top_item.isExpanded() and viewport_rect.intersects(child_rect):
                    visible_items.append(child_item)

                # Check grandchildren (level 3) if child is expanded
                if child_item.isExpanded():
                    for k in range(child_item.childCount()):
                        grandchild_item = child_item.child(k)
                        grandchild_rect = self.image_tree.visualItemRect(grandchild_item)

                        if viewport_rect.intersects(grandchild_rect):
                            visible_items.append(grandchild_item)

        return visible_items

    def _load_next_batch(self):
        """Load next batch of thumbnails in background"""
        if not self._pending_thumbnail_indices:
            self._lazy_load_timer.stop()
            return

        # Load next batch
        batch = self._pending_thumbnail_indices[:self._lazy_load_batch_size]
        self._pending_thumbnail_indices = self._pending_thumbnail_indices[self._lazy_load_batch_size:]

        for idx in batch:
            if idx < self.image_tree.topLevelItemCount():
                item = self.image_tree.topLevelItem(idx)
                widget = self.image_tree.itemWidget(item, 0)
                if widget and hasattr(widget, 'load_thumbnail_if_needed'):
                    widget.load_thumbnail_if_needed()
                # Also check child items (related images)
                for j in range(item.childCount()):
                    child = item.child(j)

                    # Load category item thumbnail if it has one
                    child_widget = self.image_tree.itemWidget(child, 0)
                    if child_widget and hasattr(child_widget, 'load_thumbnail_if_needed'):
                        child_widget.load_thumbnail_if_needed()

                    # Load grandchildren thumbnails (actual related images)
                    for k in range(child.childCount()):
                        grandchild = child.child(k)
                        grandchild_widget = self.image_tree.itemWidget(grandchild, 0)
                        if grandchild_widget and hasattr(grandchild_widget, 'load_thumbnail_if_needed'):
                            grandchild_widget.load_thumbnail_if_needed()

        # Stop timer if no more pending items
        if not self._pending_thumbnail_indices:
            self._lazy_load_timer.stop()

    def _on_scroll(self):
        """Handle scroll event - load newly visible thumbnails immediately"""
        if not self._lazy_load_enabled:
            return

        # Get currently visible items (including children)
        visible_items = self._get_visible_items()

        # Load any visible items that haven't been loaded yet
        for item in visible_items:
            # For all items (including disabled ones), check if they have widgets with thumbnails
            widget = self.image_tree.itemWidget(item, 0)
            if widget and hasattr(widget, 'load_thumbnail_if_needed'):
                widget.load_thumbnail_if_needed()

            # Also check if this is a parent item and load children if expanded
            if item.isExpanded():
                for j in range(item.childCount()):
                    child = item.child(j)
                    child_widget = self.image_tree.itemWidget(child, 0)
                    if child_widget and hasattr(child_widget, 'load_thumbnail_if_needed'):
                        child_widget.load_thumbnail_if_needed()

                    # Load grandchildren if child is expanded
                    if child.isExpanded():
                        for k in range(child.childCount()):
                            grandchild = child.child(k)
                            grandchild_widget = self.image_tree.itemWidget(grandchild, 0)
                            if grandchild_widget and hasattr(grandchild_widget, 'load_thumbnail_if_needed'):
                                grandchild_widget.load_thumbnail_if_needed()

    def _on_selection_changed(self):
        """Handle selection changes - only refresh if needed"""
        if self._updating:
            return

        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Check if filtered view changed - if so, do full refresh
        current_images = current_view.get_all_paths()
        current_filtered = tuple(current_images)
        if current_filtered != self._last_filtered_images:
            self._last_filtered_images = current_filtered
            self.refresh()
            return

        # Check if selected images changed - if so, update checkboxes
        # Also update captions in case they changed due to tag edits
        selected_images = current_view.get_selected()
        for i in range(self.image_tree.topLevelItemCount()):
            item = self.image_list.item(i)
            widget = self.image_list.itemWidget(item)
            if widget and hasattr(widget, 'checkbox'):
                img_path = item.data(0, Qt.UserRole)

                # Update checkbox state
                is_selected = img_path in selected_images
                if widget.checkbox.isChecked() != is_selected:
                    self._updating = True
                    widget.checkbox.setChecked(is_selected)
                    self._updating = False

                # Update caption if it changed
                if hasattr(widget, 'caption_label'):
                    img_data = self.app_manager.load_image_data(img_path)
                    new_caption = img_data.caption if img_data.caption else ""
                    if widget.caption != new_caption:
                        widget.caption = new_caption
                        widget.caption_label.setText(new_caption if new_caption else "(no caption)")


        # Don't force selection synchronization - let user navigate freely
        # The active image is shown in main window, but tree selection stays where user navigates

    def eventFilter(self, obj, event):
        """Event filter to intercept keyboard events from the tree widget"""
        if obj == self.image_tree and event.type() == QEvent.KeyPress:
            key = event.key()
            current_item = self.image_tree.currentItem()

            if key == Qt.Key_Space and current_item:
                # Toggle selection for active image
                widget = self.image_tree.itemWidget(current_item, 0)
                if widget and hasattr(widget, 'checkbox'):
                    # Toggle the checkbox
                    widget.checkbox.setChecked(not widget.checkbox.isChecked())
                    # Return True to prevent default space bar behavior
                    return True
            elif key == Qt.Key_Right and current_item:
                # Expand item if it has children, stay on current item
                if current_item.childCount() > 0 and not current_item.isExpanded():
                    current_item.setExpanded(True)
                    # Load thumbnails for newly visible children
                    self._load_children_thumbnails(current_item)
                    return True
            elif key == Qt.Key_Left and current_item:
                # Collapse if expanded, otherwise move to parent
                if current_item.childCount() > 0 and current_item.isExpanded():
                    current_item.setExpanded(False)
                    return True
                # If already collapsed or no children, move to parent
                parent = current_item.parent()
                if parent:
                    self.image_tree.setCurrentItem(parent)
                    return True
            elif key == Qt.Key_C:
                # Clear selection
                self._remove_all()
                return True
            elif key == Qt.Key_Delete:
                # Remove images from project
                self._delete_images()
                return True

        # Pass other events to parent
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        """Handle keyboard events at window level"""
        # This is a fallback if the list widget doesn't have focus
        current_row = self.image_list.currentRow()
        item = self.image_list.item(current_row)

        if event.key() == Qt.Key_Space and item:
            # Toggle selection for active image
            widget = self.image_list.itemWidget(item)
            if widget and hasattr(widget, 'checkbox'):
                # Toggle the checkbox
                widget.checkbox.setChecked(not widget.checkbox.isChecked())
                # Accept event to prevent default space bar behavior (scrolling)
                event.accept()
                return
        elif event.key() == Qt.Key_C:
            # Clear selection
            self._remove_all()
            event.accept()
            return
        elif event.key() == Qt.Key_Delete:
            # Remove images from project
            self._delete_images()
            event.accept()
            return

        # Pass other keys to parent (includes arrow keys for navigation)
        super().keyPressEvent(event)

    def _delete_images(self):
        """Delete selected images (or active image) from project with confirmation"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Determine which images to delete
        images_to_delete = current_view.get_working_images()
        if not images_to_delete:
            return

        count = len(images_to_delete)
        selected_images = current_view.get_selected()

        # Only show confirmation if there's a selection (multiple images potentially)
        # For single active image with no selection, delete immediately
        if selected_images:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("Remove Images")
            msg_box.setText(f"Remove {count} image{'s' if count != 1 else ''} from the project?")
            msg_box.setInformativeText("This will remove the images from the project but not delete the files.")
            msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            msg_box.setDefaultButton(QMessageBox.Ok)

            # Customize button text
            msg_box.button(QMessageBox.Ok).setText("Remove")

            result = msg_box.exec_()

            if result != QMessageBox.Ok:
                return

        # Capture current row before deletion to determine next active image
        current_row = self.image_list.currentRow()

        # Remove images from project data
        removed_count = self.app_manager.remove_images_from_project(images_to_delete)

        if removed_count == 0:
            return

        # Incremental deletion: Remove items from list without full rebuild
        self._updating = True

        # Build set for fast lookup
        images_to_delete_set = set(images_to_delete)

        # Track the first deleted row index to determine new active image
        first_deleted_row = None

        # Remove items in reverse order to avoid index shifting issues
        for i in range(self.image_tree.topLevelItemCount() - 1, -1, -1):
            item = self.image_list.item(i)
            img_path = item.data(0, Qt.UserRole)
            if img_path in images_to_delete_set:
                if first_deleted_row is None or i < first_deleted_row:
                    first_deleted_row = i
                # Remove the item widget
                self.image_list.takeItem(i)

        # Update image count
        images = current_view.get_all_paths()
        self._last_filtered_images = tuple(images)
        self.info_label.setText(f"Gallery: {len(images)} images")

        # Determine and set new active image
        new_row = None
        if self.image_tree.topLevelItemCount() > 0:
            # Try to use the same row index (which now points to the next image)
            if first_deleted_row is not None:
                new_row = min(first_deleted_row, self.image_tree.topLevelItemCount() - 1)
            else:
                new_row = 0

            # Get the image path at the new row and set it as active
            new_item = self.image_list.item(new_row)
            if new_item:
                new_active_path = new_item.data(0, Qt.UserRole)
                current_view.set_active(new_active_path)

                # Update the gallery's current row to highlight the new active image
                self.image_list.setCurrentRow(new_row)

        self._updating = False

        # Clear any selection after deletion
        current_view.clear_selection()

        # Notify project changed to update image viewer
        self.app_manager.update_project()

    def _delete_images_and_files(self):
        """Delete selected images from project AND filesystem with confirmation"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Determine which images to delete
        images_to_delete = current_view.get_working_images()
        if not images_to_delete:
            return

        count = len(images_to_delete)

        # Always show confirmation for filesystem deletion
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Delete Images from Filesystem")
        msg_box.setText(f"PERMANENTLY DELETE {count} image{'s' if count != 1 else ''} from filesystem?")
        msg_box.setInformativeText(
            "This will delete the images, .txt, and .json files from the filesystem.\n"
            "This action CANNOT be undone!"
        )
        msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg_box.setDefaultButton(QMessageBox.Cancel)

        # Customize button text
        msg_box.button(QMessageBox.Ok).setText("Delete Forever")

        result = msg_box.exec_()

        if result != QMessageBox.Ok:
            return

        # Delete images and associated files from filesystem
        deleted_count = 0
        for img_path in images_to_delete:
            try:
                # Delete image file
                if img_path.exists():
                    img_path.unlink()

                # Delete .txt file if exists
                txt_path = img_path.with_suffix('.txt')
                if txt_path.exists():
                    txt_path.unlink()

                # Delete .json file if exists
                json_path = img_path.with_suffix('.json')
                if json_path.exists():
                    json_path.unlink()

                deleted_count += 1
            except Exception as e:
                print(f"Error deleting {img_path}: {e}")

        # Remove from project
        removed_count = self.app_manager.remove_images_from_project(images_to_delete)

        # Incremental deletion from gallery
        self._updating = True

        # Build set for fast lookup
        images_to_delete_set = set(images_to_delete)

        # Track the first deleted row index
        first_deleted_row = None

        # Remove items in reverse order
        for i in range(self.image_tree.topLevelItemCount() - 1, -1, -1):
            item = self.image_list.item(i)
            img_path = item.data(0, Qt.UserRole)
            if img_path in images_to_delete_set:
                if first_deleted_row is None or i < first_deleted_row:
                    first_deleted_row = i
                self.image_list.takeItem(i)

        # Update image count
        images = current_view.get_all_paths()
        self._last_filtered_images = tuple(images)
        self.info_label.setText(f"Gallery: {len(images)} images")

        # Determine and set new active image
        new_row = None
        if self.image_tree.topLevelItemCount() > 0:
            if first_deleted_row is not None:
                new_row = min(first_deleted_row, self.image_tree.topLevelItemCount() - 1)
            else:
                new_row = 0

            # Get the image path at the new row and set it as active
            new_item = self.image_list.item(new_row)
            if new_item:
                new_active_path = new_item.data(0, Qt.UserRole)
                current_view.set_active(new_active_path)
                self.image_list.setCurrentRow(new_row)

        self._updating = False

        # Clear selection
        current_view.clear_selection()

        # Notify project changed
        self.app_manager.update_project()

        QMessageBox.information(
            self,
            "Deletion Complete",
            f"Deleted {deleted_count} image(s) from filesystem."
        )

    def _copy_image_paths(self):
        """Copy selected image paths to clipboard"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Get selected images
        images_to_copy = current_view.get_working_images()
        if not images_to_copy:
            QMessageBox.information(self, "No Selection", "No images selected to copy.")
            return

        # Convert paths to strings (absolute paths, one per line)
        path_strings = [str(img_path.resolve()) for img_path in images_to_copy]
        paths_text = "\n".join(path_strings)

        # Copy to clipboard
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(paths_text)

        QMessageBox.information(
            self,
            "Paths Copied",
            f"Copied {len(images_to_copy)} image path(s) to clipboard.\n\n"
            "You can now paste these paths into the Import dialog."
        )

    def _update_source_selector(self):
        """Update the source selector dropdown with available sources"""
        self.source_combo.clear()

        try:
            current_view = self.app_manager.get_current_view()
            if current_view is None:
                self.source_combo.addItem("No Source")
                return

            # Add current source
            if hasattr(self.app_manager, 'current_view_mode') and self.app_manager.current_view_mode == "library":
                self.source_combo.addItem("Library")
            else:
                self.source_combo.addItem("Current Project")

            # Add library if not in library mode
            if hasattr(self.app_manager, 'current_view_mode') and self.app_manager.current_view_mode != "library":
                self.source_combo.addItem("Library")

            # Add other projects
            library = self.app_manager.get_library()
            if library and hasattr(library, 'list_projects'):
                try:
                    for project_name in library.list_projects():
                        self.source_combo.addItem(f"Project: {project_name}")
                except Exception:
                    pass  # Skip if can't list projects
        except Exception:
            # Fallback if any error occurs
            self.source_combo.addItem("Current Source")

    def _on_source_changed(self, source_text: str):
        """Handle source selector change"""
        # This will rebuild the tree with related images from the selected source
        self.refresh()

    def _on_checkbox_clicked(self, img_path: Path, state: int):
        """Handle checkbox click - toggle image selection"""
        if self._updating:
            return

        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Use the proper toggle_selection method
        current_view.toggle_selection(img_path)

        # Emit selection changed to update UI
        self.app_manager.update_project(save=False)

    def _on_item_changed(self, current_item: 'QTreeWidgetItem', previous_item: 'QTreeWidgetItem'):
        """Handle tree item selection change - distinguish between active item and active image"""
        if self._updating:
            return

        if current_item:
            # Check if this is a category item (Level 2)
            if current_item.data(0, Qt.UserRole + 1) == "category":
                # This is a category folder - it can be the active item but doesn't set active image
                return

            # Check if this has an image path (Level 1 or Level 3 image items)
            img_path = current_item.data(0, Qt.UserRole)
            if img_path:
                # This is an actual image item - set it as the active image
                current_view = self.app_manager.get_current_view()
                if current_view is not None:
                    current_view.set_active(img_path)
                    self.app_manager.update_project(save=False)

    def _on_item_double_clicked(self, item: 'QTreeWidgetItem', column: int):
        """Handle double-click on tree items - toggle expansion"""
        if item and item.childCount() > 0:
            # Only toggle expansion for items that have children
            item.setExpanded(not item.isExpanded())
            # If we expanded an item, trigger thumbnail loading for its children
            if item.isExpanded():
                self._load_children_thumbnails(item)

    def _load_children_thumbnails(self, parent_item: 'QTreeWidgetItem'):
        """Load thumbnails for all children and grandchildren of an item"""
        for j in range(parent_item.childCount()):
            child = parent_item.child(j)
            child_widget = self.image_tree.itemWidget(child, 0)
            if child_widget and hasattr(child_widget, 'load_thumbnail_if_needed'):
                child_widget.load_thumbnail_if_needed()

            # Load grandchildren if child has them
            for k in range(child.childCount()):
                grandchild = child.child(k)
                grandchild_widget = self.image_tree.itemWidget(grandchild, 0)
                if grandchild_widget and hasattr(grandchild_widget, 'load_thumbnail_if_needed'):
                    grandchild_widget.load_thumbnail_if_needed()

    def _on_item_expanded(self, item: 'QTreeWidgetItem'):
        """Handle tree item expansion - load thumbnails for newly visible items"""
        self._load_children_thumbnails(item)

    def _on_item_collapsed(self, item: 'QTreeWidgetItem'):
        """Handle tree item collapse - no special action needed"""
        pass

    def _build_tree(self, images):
        """Build the tree structure with main images and related images"""
        self.image_tree.clear()

        try:
            current_source = self.source_combo.currentText()
        except Exception:
            current_source = "Current"

        for img_path in images:
            try:
                # Load image data
                img_data = self.app_manager.load_image_data(img_path)
                img_name = img_data.name if img_data.name else img_path.stem
                img_caption = img_data.caption if img_data.caption else ""

                # Determine source
                if hasattr(self.app_manager, 'current_view_mode') and self.app_manager.current_view_mode == "library":
                    source = "Library"
                else:
                    source = "Current Project"

                # Create main tree item
                main_item = QTreeWidgetItem(self.image_tree)
                main_item.setData(0, Qt.UserRole, img_path)

                # Create widget for main item
                widget = GalleryTreeItemWidget(
                    img_path, img_name, img_caption,
                    self.size_slider.value(), lazy_load=self._lazy_load_enabled
                )

                # Connect checkbox
                widget.checkbox.stateChanged.connect(lambda state, path=img_path: self._on_checkbox_clicked(path, state))

                self.image_tree.setItemWidget(main_item, 0, widget)

                # Add related images as children if they exist
                if hasattr(img_data, 'related') and img_data.related:
                    for rel_type, rel_paths in img_data.related.items():
                        if rel_paths:  # Only show relationship types that have images
                            # Create relationship category item (Level 2 - navigable but doesn't set active image)
                            rel_item = QTreeWidgetItem(main_item)
                            rel_item.setText(0, f"📁 {rel_type.title()} ({len(rel_paths)})")
                            # Keep enabled for navigation but mark as category type
                            rel_item.setData(0, Qt.UserRole + 1, "category")  # Mark as category item

                            # Add related images as children
                            for rel_path in rel_paths:
                                try:
                                    rel_path_obj = Path(rel_path)
                                    if rel_path_obj.exists():  # Only show if file exists
                                        rel_child = QTreeWidgetItem(rel_item)
                                        rel_child.setData(0, Qt.UserRole, rel_path_obj)

                                        # Get related image data
                                        rel_data = self.app_manager.load_image_data(rel_path_obj)
                                        rel_name = rel_data.name if rel_data.name else rel_path_obj.stem
                                        rel_caption = rel_data.caption if rel_data.caption else ""

                                        # Determine related image source
                                        rel_source = self._get_image_source(rel_path_obj)

                                        # Create widget for related image
                                        rel_widget = GalleryTreeItemWidget(
                                            rel_path_obj, rel_name, rel_caption,
                                            self.size_slider.value(), lazy_load=self._lazy_load_enabled
                                        )

                                        # Connect checkbox
                                        rel_widget.checkbox.stateChanged.connect(lambda state, path=rel_path_obj: self._on_checkbox_clicked(path, state))

                                        self.image_tree.setItemWidget(rel_child, 0, rel_widget)

                                        # No need to set other columns since we're using custom widgets in column 0 only
                                except Exception:
                                    # Skip related image if error occurs
                                    continue
            except Exception:
                # Skip main image if error occurs
                continue

        # Start with all trees collapsed (only level 1 visible)
        # Remove auto-expand so users can navigate as specified

        # Trigger loading of visible thumbnails
        if self._lazy_load_enabled:
            self._on_scroll()

        # Don't auto-select active image - let user navigate freely
        # The active image will still show in main window, but tree selection stays where user is

    def _get_image_source(self, img_path: Path) -> str:
        """Determine the source of an image (Library or Project)"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return "Unknown"

        # Check if image is in current view
        if img_path in current_view.get_all_paths():
            if self.app_manager.current_view_mode == "library":
                return "Library"
            else:
                return "Current Project"

        # Check if image is in library
        library = self.app_manager.get_library()
        if library and library.library_image_list and img_path in library.library_image_list.get_all_paths():
            return "Library"

        # Check projects
        if library:
            for project_name in library.list_projects():
                project = library.get_project(project_name)
                if project and img_path in project.image_list.get_all_paths():
                    return f"Project: {project_name}"

        return "Unknown"
