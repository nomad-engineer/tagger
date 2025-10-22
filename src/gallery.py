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
from typing import List
from .data_models import ImageList


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

        # Initialize view selector
        self._update_view_selector()
        # Connect to library changes to update view selector
        self.app_manager.library_changed.connect(self._update_view_selector)

        # Initial load
        self.refresh()

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

        # Gallery header with status and controls
        header_layout = QHBoxLayout()

        # Status display (left side)
        self.status_label = QLabel("No selection")
        self.status_label.setStyleSheet("font-weight: bold; color: #666;")
        header_layout.addWidget(self.status_label)

        header_layout.addStretch()

        # View selector (center)
        header_layout.addWidget(QLabel("View:"))
        self.view_selector = QComboBox()
        self.view_selector.setMinimumWidth(200)
        self.view_selector.currentIndexChanged.connect(self._on_view_changed)
        header_layout.addWidget(self.view_selector)

        header_layout.addStretch()

        # Action buttons (right side)
        self.sort_btn = QPushButton("Sort by Likeness")
        self.sort_btn.setToolTip("Sort images by visual similarity")
        self.sort_btn.clicked.connect(self._open_sort_dialog)
        header_layout.addWidget(self.sort_btn)

        layout.addLayout(header_layout)

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

        self.add_to_project_btn = QPushButton("Add to Project")
        self.add_to_project_btn.setToolTip("Add selected images to a project")
        self.add_to_project_btn.clicked.connect(self._add_to_project)
        controls_row2.addWidget(self.add_to_project_btn)

        controls_row2.addStretch()

        layout.addLayout(controls_row2)

        # Keyboard hints
        keyboard_hint = QLabel("Keyboard: ↑↓ navigate • Space toggle select • C clear all • Del remove")
        keyboard_hint.setStyleSheet("color: gray; font-size: 9px;")
        keyboard_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(keyboard_hint)

    def _update_status_display(self):
        """Update the status label with selection count or active image"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            self.status_label.setText("No view loaded")
            self.status_label.setStyleSheet("font-weight: bold; color: #666;")
            return

        selected_images = current_view.get_selected()
        if selected_images:
            count = len(selected_images)
            self.status_label.setText(f"{count} image{'s' if count != 1 else ''} selected")
        else:
            active_image = current_view.get_active()
            if active_image:
                self.status_label.setText(f"Active: {active_image.name}")
            else:
                self.status_label.setText("No selection")

        # Ensure normal color (unless we're loading)
        current_style = self.status_label.styleSheet()
        if "color: #2196F3" not in current_style:  # Don't override loading color
            self.status_label.setStyleSheet("font-weight: bold; color: #666;")

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
            self.status_label.setText("No library or project loaded")
            self._updating = False
            return

        # Get images from current view (filtered or all)
        images = current_view.get_all_paths()
        self._last_filtered_images = tuple(images)

        # Show loading progress in status
        self.status_label.setText(f"Loading {len(images)} images...")
        self.status_label.setStyleSheet("font-weight: bold; color: #2196F3;")  # Blue color to indicate loading

        # Force UI update
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        # Allow UI to update before building tree
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(10, lambda: self._build_tree_with_progress(images))

    def _build_tree_with_progress(self, images):
        """Build tree with progress updates"""
        try:
            # Build basic tree structure
            self._build_tree(images)

            # Set initial active image if none set
            current_view = self.app_manager.get_current_view()
            if current_view and images and current_view.get_active() is None:
                current_view.set_active(images[0])

            # Update status when complete
            self._update_status_display()
            # Reset color to normal
            self.status_label.setStyleSheet("font-weight: bold; color: #666;")

            # Lazy loading disabled temporarily to improve performance
            # TODO: Optimize lazy loading to avoid slow scrolling
            # if self._lazy_load_enabled:
            #     self._start_lazy_loading()

        finally:
            self._updating = False

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
            item = self.image_tree.topLevelItem(i)
            widget = self.image_tree.itemWidget(item, 0)
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


        # Update status display
        self._update_status_display()

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
        """Delete selected images (or active image) from current view with confirmation"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Determine which images to delete
        images_to_delete = current_view.get_working_images()
        if not images_to_delete:
            return

        count = len(images_to_delete)
        selected_images = current_view.get_selected()

        # Only show confirmation if there's a selection (multiple images)
        # For single active image with no selection, delete immediately
        if selected_images:
            # Create detailed confirmation message
            view_type = "project" if self.app_manager.current_view_mode == "project" else "library"
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle(f"Remove from {view_type.title()}")

            # Main message
            msg_box.setText(f"Remove {count} image{'s' if count != 1 else ''} from the {view_type}?")

            # Detailed information with filenames
            filenames_text = "\n".join([img.name for img in images_to_delete[:10]])
            if count > 10:
                filenames_text += f"\n... and {count - 10} more"

            msg_box.setInformativeText(f"This will remove:\n\n{filenames_text}")
            msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            msg_box.setDefaultButton(QMessageBox.Cancel)

            # Customize button text
            msg_box.button(QMessageBox.Ok).setText("Remove")

            result = msg_box.exec_()
            if result != QMessageBox.Ok:
                return

        # Remove images from current view
        if self.app_manager.current_view_mode == "project":
            # Remove from project (images stay in library)
            removed_count = self.app_manager.remove_images_from_project(images_to_delete)
        else:
            # Remove from library
            library = self.app_manager.get_library()
            if library and library.library_image_list:
                removed_count = library.library_image_list.remove_images(images_to_delete)
                # Track library changes
                self.app_manager.pending_changes.mark_library_modified()
                for img_path in images_to_delete:
                    self.app_manager.pending_changes.mark_image_removed(img_path)
            else:
                removed_count = 0

        if removed_count == 0:
            return

        # Update gallery more efficiently - avoid full rebuild
        self._remove_items_from_gallery(images_to_delete)

    # Delete from disk functionality removed - simplified deletion only

    def _remove_items_from_gallery(self, images_to_remove):
        """Efficiently remove items from gallery without full rebuild"""
        if not images_to_remove:
            return

        images_to_remove_set = set(images_to_remove)
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        self._updating = True

        # Remove items in reverse order to avoid index shifting
        for i in range(self.image_tree.topLevelItemCount() - 1, -1, -1):
            item = self.image_tree.topLevelItem(i)
            img_path = item.data(0, Qt.UserRole)
            if img_path in images_to_remove_set:
                self.image_tree.takeTopLevelItem(i)

        # Update image count
        remaining_images = current_view.get_all_paths()
        self._last_filtered_images = tuple(remaining_images)
        self._update_status_display()

        # Set new active image if needed
        if current_view.get_active() in images_to_remove_set:
            # Try to select the next available image
            if self.image_tree.topLevelItemCount() > 0:
                first_item = self.image_tree.topLevelItem(0)
                new_active_path = first_item.data(0, Qt.UserRole)
                current_view.set_active(new_active_path)
                self.image_tree.setCurrentItem(first_item)

        self._updating = False

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

    # Source selector methods removed - functionality moved to view selector

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
        """Build simple tree structure with main images only (no related images)"""
        self.image_tree.clear()

        total_images = len(images)
        processed_count = 0
        update_interval = max(1, total_images // 20)  # Update status every 5% of images

        for img_path in images:
            try:
                # Load image data
                img_data = self.app_manager.load_image_data(img_path)
                img_name = img_data.name if img_data.name else img_path.stem
                img_caption = img_data.caption if img_data.caption else ""

                # Create tree item (flat structure - no children)
                main_item = QTreeWidgetItem(self.image_tree)
                main_item.setData(0, Qt.UserRole, img_path)

                # Create widget for item (avoid recaching by using existing data)
                widget = GalleryTreeItemWidget(
                    img_path, img_name, img_caption,
                    self.size_slider.value(), lazy_load=self._lazy_load_enabled
                )

                # Connect checkbox
                widget.checkbox.stateChanged.connect(lambda state, path=img_path: self._on_checkbox_clicked(path, state))

                self.image_tree.setItemWidget(main_item, 0, widget)

                processed_count += 1

                # Update status periodically
                if processed_count % update_interval == 0 or processed_count == total_images:
                    progress = (processed_count / total_images) * 100
                    self.status_label.setText(f"Loading: {processed_count}/{total_images} ({progress:.0f}%)")
                    self.status_label.setStyleSheet("font-weight: bold; color: #2196F3;")  # Blue during loading
                    # Allow UI to update
                    from PyQt5.QtWidgets import QApplication
                    QApplication.processEvents()

            except Exception:
                # Skip image if error occurs
                processed_count += 1
                continue

        # Trigger loading of visible thumbnails if lazy loading is disabled
        if not self._lazy_load_enabled:
            self._on_scroll()

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

    # View selector methods (moved from main window)
    def _update_view_selector(self):
        """Update the view selector dropdown with library and projects"""
        # Block signals to avoid triggering view changes during update
        self.view_selector.blockSignals(True)

        self.view_selector.clear()

        library = self.app_manager.get_library()
        if not library:
            self.view_selector.addItem("(No library loaded)")
            self.view_selector.setEnabled(False)
            self.view_selector.blockSignals(False)
            return

        self.view_selector.setEnabled(True)

        # Add "Whole Library" option
        self.view_selector.addItem("Whole Library")

        # Add all projects
        projects = library.list_projects()
        for project_name in sorted(projects):
            self.view_selector.addItem(project_name)

        # Set current selection based on view mode
        current_view_name = self.app_manager.get_current_view_name()
        index = self.view_selector.findText(current_view_name)
        if index >= 0:
            self.view_selector.setCurrentIndex(index)

        self.view_selector.blockSignals(False)

    def _on_view_changed(self, index):
        """Handle view selector change"""
        if index < 0:
            return

        view_name = self.view_selector.currentText()

        if view_name == "Whole Library":
            self.app_manager.switch_to_library_view()
            # Update status in main window
            main_window = self.parent()
            while main_window and hasattr(main_window, 'parent'):
                if hasattr(main_window, 'statusBar'):
                    main_window.statusBar().showMessage("Viewing: Whole Library", 2000)
                    break
                main_window = main_window.parent()
        elif view_name and view_name != "(No library loaded)":
            self.app_manager.switch_to_project_view(view_name)
            # Update status in main window
            main_window = self.parent()
            while main_window and hasattr(main_window, 'parent'):
                if hasattr(main_window, 'statusBar'):
                    main_window.statusBar().showMessage(f"Viewing project: {view_name}", 2000)
                    break
                main_window = main_window.parent()

    # Placeholder methods for new functionality
    def _open_sort_dialog(self):
        """Open the Sort by Likeness dialog"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            QMessageBox.warning(self, "No View", "Please select a view (library or project) first.")
            return

        images = current_view.get_all_paths()
        if not images:
            QMessageBox.information(self, "No Images", "No images to sort in the current view.")
            return

        # Create sort dialog
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSlider, QPushButton, QDialogButtonBox, QProgressBar, QTextEdit, QGroupBox
        from PIL import Image
        import imagehash

        dialog = QDialog(self)
        dialog.setWindowTitle("Sort by Likeness")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)

        layout = QVBoxLayout(dialog)

        # Algorithm selection
        algo_group = QGroupBox("Hash Algorithm")
        algo_layout = QHBoxLayout(algo_group)

        algo_layout.addWidget(QLabel("Algorithm:"))
        algo_combo = QComboBox()
        algo_combo.addItems(["Perceptual Hash (pHash)", "Difference Hash (dHash)", "Average Hash (Average)", "Wavelet Hash (wHash)"])
        algo_layout.addWidget(algo_combo)

        layout.addWidget(algo_group)

        # Threshold slider
        threshold_group = QGroupBox("Likeness Threshold")
        threshold_layout = QVBoxLayout(threshold_group)

        threshold_info = QLabel("Lower values = more similar (recommended: 5-15)")
        threshold_info.setStyleSheet("color: #666; font-size: 10px;")
        threshold_layout.addWidget(threshold_info)

        slider_layout = QHBoxLayout()
        slider_layout.addWidget(QLabel("Threshold:"))
        threshold_slider = QSlider(Qt.Horizontal)
        threshold_slider.setMinimum(0)
        threshold_slider.setMaximum(50)
        threshold_slider.setValue(10)
        threshold_slider.setMaximumWidth(200)
        slider_layout.addWidget(threshold_slider)
        threshold_value_label = QLabel("10")
        slider_layout.addWidget(threshold_value_label)
        slider_layout.addStretch()
        threshold_layout.addLayout(slider_layout)

        layout.addWidget(threshold_group)

        # Progress bar and results
        progress_bar = QProgressBar()
        progress_bar.setVisible(False)
        layout.addWidget(progress_bar)

        results_text = QTextEdit()
        results_text.setMaximumHeight(150)
        results_text.setReadOnly(True)
        layout.addWidget(results_text)

        # Update threshold label when slider changes
        def update_threshold_label(value):
            threshold_value_label.setText(str(value))

        threshold_slider.valueChanged.connect(update_threshold_label)

        # Sort function
        def sort_images():
            algorithm_map = {
                0: imagehash.phash,    # pHash
                1: imagehash.dhash,    # dHash
                2: imagehash.average_hash,  # Average
                3: imagehash.whash     # wHash
            }

            hash_func = algorithm_map[algo_combo.currentIndex()]
            threshold = threshold_slider.value()

            # Disable controls during processing
            algo_group.setEnabled(False)
            threshold_group.setEnabled(False)
            progress_bar.setVisible(True)
            progress_bar.setMaximum(len(images))
            progress_bar.setValue(0)
            results_text.clear()

            # Hash all images
            image_hashes = {}
            errors = []

            results_text.append(f"Hashing {len(images)} images with {algo_combo.currentText()}...")

            for idx, img_path in enumerate(images):
                try:
                    img_hash = hash_func(Image.open(img_path))
                    image_hashes[img_path] = img_hash
                except Exception as e:
                    errors.append(f"Error hashing {img_path.name}: {e}")

                progress_bar.setValue(idx + 1)
                # Keep UI responsive using QApplication static method
                from PyQt5.QtWidgets import QApplication
                QApplication.processEvents()

            if not image_hashes:
                results_text.append("No valid images could be hashed.")
                return

            results_text.append(f"Successfully hashed {len(image_hashes)} images.")
            if errors:
                results_text.append(f"Encountered {len(errors)} errors.")

            # Sort by likeness
            results_text.append("\nSorting by likeness...")
            sorted_images = []
            unprocessed = set(image_hashes.keys())

            while unprocessed:
                # Take first unprocessed image
                current_img = unprocessed.pop()
                sorted_images.append(current_img)
                current_hash = image_hashes[current_img]

                # Find similar images
                similar_images = []
                remaining = list(unprocessed)

                for img_path in remaining:
                    distance = abs(current_hash - image_hashes[img_path])
                    if distance <= threshold:
                        similar_images.append(img_path)
                        unprocessed.remove(img_path)

                # Add similar images (sorted by distance)
                similar_images.sort(key=lambda x: abs(current_hash - image_hashes[x]))
                sorted_images.extend(similar_images)

                results_text.append(f"Group {len(sorted_images) - len(similar_images)}: {current_img.name} + {len(similar_images)} similar")

            # Update gallery
            results_text.append(f"\nSorting complete! Created {len([g for g in range(len(sorted_images)) if g == 0 or abs(image_hashes[sorted_images[g-1]] - image_hashes[sorted_images[g]]) > threshold])} likeness groups.")

            # Apply the sorted order to the current view
            success = self._apply_sorted_order_to_view(sorted_images)
            if success:
                results_text.append(f"\n✅ Gallery reordered successfully!")
                results_text.append(f"Created {len([g for g in range(len(sorted_images)) if g == 0 or abs(image_hashes[sorted_images[g-1]] - image_hashes[sorted_images[g]]) > threshold])} likeness groups.")
            else:
                results_text.append(f"\n❌ Failed to reorder gallery")
                results_text.append("This could be due to view limitations.")

            # Re-enable controls
            algo_group.setEnabled(True)
            threshold_group.setEnabled(True)
            progress_bar.setVisible(False)

        # Dialog buttons
        button_layout = QHBoxLayout()
        sort_btn = QPushButton("Sort Images")
        sort_btn.clicked.connect(sort_images)
        button_layout.addWidget(sort_btn)
        button_layout.addStretch()

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        button_layout.addWidget(button_box)

        layout.addLayout(button_layout)

        # Show dialog
        dialog.exec_()

    def _apply_sorted_order_to_view(self, sorted_images: List[Path]) -> bool:
        """Apply the sorted image order to the current view"""
        try:
            current_view = self.app_manager.get_current_view()
            if current_view is None:
                print("❌ No current view")
                return False

            # Check if current_view IS an ImageList (new architecture) or has an image_list (legacy)
            if isinstance(current_view, ImageList):
                # This is the new architecture where current_view is directly an ImageList
                success = current_view.set_order(sorted_images)
                if success:
                    # Mark as modified and refresh gallery
                    if self.app_manager.current_view_mode == "project":
                        self.app_manager.pending_changes.mark_project_modified()
                    else:
                        self.app_manager.pending_changes.mark_library_modified()

                    # Refresh gallery to show new order
                    self.refresh()
                return success
            elif hasattr(current_view, 'image_list') and current_view.image_list:
                # Legacy architecture where view has an image_list attribute
                success = current_view.image_list.set_order(sorted_images)
                if success:
                    if self.app_manager.current_view_mode == "project":
                        self.app_manager.pending_changes.mark_project_modified()
                    else:
                        self.app_manager.pending_changes.mark_library_modified()
                    self.refresh()
                return success
            else:
                print("❌ Current view is neither ImageList nor has image_list attribute")
                return False

        except Exception as e:
            print(f"❌ Exception in _apply_sorted_order_to_view: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _add_to_project(self):
        """Add selected images to a project"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Get selected images (or active image if no selection)
        images_to_add = current_view.get_working_images()
        if not images_to_add:
            QMessageBox.information(self, "No Images", "Please select images to add to a project.")
            return

        # Get available projects
        library = self.app_manager.get_library()
        if not library:
            QMessageBox.warning(self, "No Library", "No library is loaded. Please load a library first.")
            return

        projects = library.list_projects()
        if not projects:
            QMessageBox.warning(self, "No Projects", "No projects found. Please create a project first.")
            return

        # Create project selection dialog
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Add to Project")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # Info label
        count = len(images_to_add)
        info_label = QLabel(f"Add {count} image{'s' if count != 1 else ''} to project:")
        layout.addWidget(info_label)

        # Project list
        project_list = QListWidget()
        for project_name in sorted(projects):
            item = QListWidgetItem(project_name)
            project_list.addItem(item)
        project_list.setCurrentRow(0)  # Select first project by default
        layout.addWidget(project_list)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog
        if dialog.exec_() != QDialog.Accepted:
            return

        # Get selected project
        selected_items = project_list.selectedItems()
        if not selected_items:
            return

        project_name = selected_items[0].text()
        project = library.get_project(project_name)
        if not project:
            QMessageBox.warning(self, "Error", f"Could not load project: {project_name}")
            return

        # Add images to project
        added_count = 0
        already_in_project = 0

        for img_path in images_to_add:
            if img_path not in project.image_list.get_all_paths():
                project.image_list.add_image(img_path)
                added_count += 1
            else:
                already_in_project += 1

        # Update project
        if added_count > 0:
            self.app_manager.update_project(save=False)  # Don't save immediately, just track changes

        # Show result
        if added_count > 0:
            message = f"Added {added_count} image{'s' if added_count != 1 else ''} to project '{project_name}'"
            if already_in_project > 0:
                message += f"\n({already_in_project} image{'s' if already_in_project != 1 else ''} were already in the project)"
            QMessageBox.information(self, "Added to Project", message)
        else:
            QMessageBox.information(self, "No Changes", f"All selected images were already in project '{project_name}'")
