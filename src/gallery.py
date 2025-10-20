"""
Gallery - Grid/List view of project images with thumbnails and selection
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QSlider, QCheckBox, QMessageBox, QScrollArea
)
from PyQt5.QtCore import Qt, QSize, QTimer, QEvent
from PyQt5.QtGui import QPixmap, QIcon, QPixmapCache
from pathlib import Path


class GalleryItemWidget(QWidget):
    """Custom widget for gallery items with thumbnail and checkbox"""

    def __init__(self, image_path: Path, image_name: str, thumbnail_size: int, lazy_load: bool = False, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.image_name = image_name
        self.thumbnail_size = thumbnail_size
        self.thumbnail_loaded = False
        self.setup_ui(lazy_load)

    def setup_ui(self, lazy_load: bool):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        # Checkbox
        self.checkbox = QCheckBox()
        layout.addWidget(self.checkbox)

        # Thumbnail
        self.thumbnail_label = QLabel()

        if not lazy_load:
            # Load immediately (legacy behavior)
            self._load_thumbnail()
        else:
            # Placeholder for lazy loading
            self.thumbnail_label.setText("...")
            self.thumbnail_label.setMinimumSize(self.thumbnail_size, self.thumbnail_size)

        layout.addWidget(self.thumbnail_label)

        # Name
        self.name_label = QLabel(self.image_name)
        layout.addWidget(self.name_label)
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
                pixmap = pixmap.scaled(self.thumbnail_size, self.thumbnail_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                # Cache the scaled thumbnail for future use
                QPixmapCache.insert(cache_key, pixmap)
                self.thumbnail_label.setPixmap(pixmap)
            else:
                self.thumbnail_label.setText("[No Image]")
        else:
            # Found in cache - use it directly
            self.thumbnail_label.setPixmap(pixmap)

        self.thumbnail_loaded = True

    def load_thumbnail_if_needed(self):
        """Public method to trigger lazy loading"""
        if not self.thumbnail_loaded:
            self._load_thumbnail()


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

        # Initial load
        self.refresh()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Info label
        self.info_label = QLabel("Gallery - Select images")
        layout.addWidget(self.info_label)

        # List widget
        self.image_list = QListWidget()
        self.image_list.currentRowChanged.connect(self._on_row_changed)
        # Connect scrollbar to trigger lazy loading of newly visible items
        self.image_list.verticalScrollBar().valueChanged.connect(self._on_scroll)
        # Install event filter to handle keyboard events
        self.image_list.installEventFilter(self)
        layout.addWidget(self.image_list)

        # Bottom controls
        controls_layout = QHBoxLayout()

        # Selection buttons
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        controls_layout.addWidget(select_all_btn)

        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.clicked.connect(self._remove_all)
        controls_layout.addWidget(clear_all_btn)

        controls_layout.addStretch()

        # Size slider
        controls_layout.addWidget(QLabel("Size:"))
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setMinimum(50)
        self.size_slider.setMaximum(300)
        self.size_slider.setValue(self.app_manager.get_config().thumbnail_size)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        self.size_slider.setMaximumWidth(150)
        controls_layout.addWidget(self.size_slider)

        layout.addLayout(controls_layout)

        # Keyboard hints
        keyboard_hint = QLabel("Keyboard: ↑↓ navigate • Space toggle select • C clear all • Del remove")
        keyboard_hint.setStyleSheet("color: gray; font-size: 9px;")
        keyboard_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(keyboard_hint)

    def refresh(self):
        """Refresh list from project"""
        if self._updating:
            return

        self._updating = True

        # Stop any pending lazy loading
        self._lazy_load_timer.stop()
        self._pending_thumbnail_indices.clear()

        project = self.app_manager.get_project()
        current_view = self.app_manager.get_current_view()

        # Clear list
        self.image_list.clear()

        if not project.project_file or current_view is None:
            self.info_label.setText("No project loaded")
            self._updating = False
            return

        # Get images from current view (filtered or all)
        images = current_view.get_all_paths()
        self._last_filtered_images = tuple(images)

        self.info_label.setText(f"Gallery: {len(images)} images")

        # Get thumbnail size
        thumbnail_size = self.size_slider.value()

        # Populate list with widgets
        for idx, img_path in enumerate(images):
            # Load image data to get name
            img_data = self.app_manager.load_image_data(img_path)
            img_name = img_data.name if img_data.name else img_path.stem

            # Create list item
            item = QListWidgetItem()
            item.setData(Qt.UserRole, img_path)  # Store image path in item
            self.image_list.addItem(item)

            # Create custom widget with lazy loading
            widget = GalleryItemWidget(img_path, img_name, thumbnail_size, lazy_load=self._lazy_load_enabled)

            # Set checkbox state (block signals to avoid triggering selection during init)
            selected_images = current_view.get_selected()
            widget.checkbox.blockSignals(True)
            widget.checkbox.setChecked(img_path in selected_images)
            widget.checkbox.blockSignals(False)

            # Connect signal after setting initial state
            widget.checkbox.stateChanged.connect(lambda state, path=img_path: self._on_checkbox_changed(path, state))

            # Set widget for item
            item.setSizeHint(widget.sizeHint())
            self.image_list.setItemWidget(item, widget)

        # Highlight active image
        active_image = current_view.get_active()
        if active_image:
            for i in range(self.image_list.count()):
                item = self.image_list.item(i)
                img_path = item.data(Qt.UserRole)
                if img_path == active_image:
                    self.image_list.setCurrentRow(i)
                    break

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
            img_path = item.data(Qt.UserRole)
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

        total_count = self.image_list.count()
        if total_count == 0:
            return

        # Get visible range
        visible_indices = self._get_visible_indices()

        # Load visible items immediately
        for idx in visible_indices:
            widget = self.image_list.itemWidget(self.image_list.item(idx))
            if widget and hasattr(widget, 'load_thumbnail_if_needed'):
                widget.load_thumbnail_if_needed()

        # Queue all remaining items for background loading
        self._pending_thumbnail_indices = [i for i in range(total_count) if i not in visible_indices]

        # Start background loading timer if there are pending items
        if self._pending_thumbnail_indices:
            self._lazy_load_timer.start(10)  # 10ms interval for smooth loading

    def _get_visible_indices(self):
        """Get indices of currently visible items in the list"""
        visible_indices = []

        # Get the viewport rect
        viewport_rect = self.image_list.viewport().rect()

        for i in range(self.image_list.count()):
            item = self.image_list.item(i)
            item_rect = self.image_list.visualItemRect(item)

            # Check if item is visible in viewport
            if viewport_rect.intersects(item_rect):
                visible_indices.append(i)

        return visible_indices

    def _load_next_batch(self):
        """Load next batch of thumbnails in background"""
        if not self._pending_thumbnail_indices:
            self._lazy_load_timer.stop()
            return

        # Load next batch
        batch = self._pending_thumbnail_indices[:self._lazy_load_batch_size]
        self._pending_thumbnail_indices = self._pending_thumbnail_indices[self._lazy_load_batch_size:]

        for idx in batch:
            if idx < self.image_list.count():
                widget = self.image_list.itemWidget(self.image_list.item(idx))
                if widget and hasattr(widget, 'load_thumbnail_if_needed'):
                    widget.load_thumbnail_if_needed()

        # Stop timer if no more pending items
        if not self._pending_thumbnail_indices:
            self._lazy_load_timer.stop()

    def _on_scroll(self):
        """Handle scroll event - load newly visible thumbnails immediately"""
        if not self._lazy_load_enabled:
            return

        # Get currently visible items
        visible_indices = self._get_visible_indices()

        # Load any visible items that haven't been loaded yet
        for idx in visible_indices:
            widget = self.image_list.itemWidget(self.image_list.item(idx))
            if widget and hasattr(widget, 'load_thumbnail_if_needed'):
                widget.load_thumbnail_if_needed()

            # Remove from pending queue if it's there
            if idx in self._pending_thumbnail_indices:
                self._pending_thumbnail_indices.remove(idx)

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
        selected_images = current_view.get_selected()
        for i in range(self.image_list.count()):
            item = self.image_list.item(i)
            widget = self.image_list.itemWidget(item)
            if widget and hasattr(widget, 'checkbox'):
                img_path = item.data(Qt.UserRole)
                is_selected = img_path in selected_images
                if widget.checkbox.isChecked() != is_selected:
                    self._updating = True
                    widget.checkbox.setChecked(is_selected)
                    self._updating = False

        # Update active image highlight
        active_image = current_view.get_active()
        if active_image:
            for i in range(self.image_list.count()):
                item = self.image_list.item(i)
                img_path = item.data(Qt.UserRole)
                if img_path == active_image:
                    if self.image_list.currentRow() != i:
                        self._updating = True
                        self.image_list.setCurrentRow(i)
                        self._updating = False
                    break

    def eventFilter(self, obj, event):
        """Event filter to intercept keyboard events from the list widget"""
        if obj == self.image_list and event.type() == QEvent.KeyPress:
            key = event.key()
            current_row = self.image_list.currentRow()
            item = self.image_list.item(current_row)

            if key == Qt.Key_Space and item:
                # Toggle selection for active image
                widget = self.image_list.itemWidget(item)
                if widget and hasattr(widget, 'checkbox'):
                    # Toggle the checkbox
                    widget.checkbox.setChecked(not widget.checkbox.isChecked())
                    # Return True to prevent default space bar behavior
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
        for i in range(self.image_list.count() - 1, -1, -1):
            item = self.image_list.item(i)
            img_path = item.data(Qt.UserRole)
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
        if self.image_list.count() > 0:
            # Try to use the same row index (which now points to the next image)
            if first_deleted_row is not None:
                new_row = min(first_deleted_row, self.image_list.count() - 1)
            else:
                new_row = 0

            # Get the image path at the new row and set it as active
            new_item = self.image_list.item(new_row)
            if new_item:
                new_active_path = new_item.data(Qt.UserRole)
                current_view.set_active(new_active_path)

                # Update the gallery's current row to highlight the new active image
                self.image_list.setCurrentRow(new_row)

        self._updating = False

        # Clear any selection after deletion
        current_view.clear_selection()

        # Notify project changed to update image viewer
        self.app_manager.update_project()
