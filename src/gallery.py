"""
Gallery - Grid/List view of project images with thumbnails and selection
"""

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QSlider,
    QCheckBox,
    QMessageBox,
    QScrollArea,
    QComboBox,
    QAbstractItemView,
    QMenu,
    QAction,
    QApplication,
)
from PyQt5.QtCore import Qt, QSize, QTimer, QEvent, QUrl, QMimeData
from PyQt5.QtGui import QPixmap, QIcon, QPixmapCache, QImage
from pathlib import Path
from typing import List
from .data_models import ImageList


class GalleryTreeItemWidget(QWidget):
    """Custom widget for gallery tree items with thumbnail, checkbox, and text info"""

    def __init__(
        self,
        image_path: Path,
        image_name: str,
        caption: str,
        thumbnail_size: int,
        lazy_load: bool = False,
        app_manager=None,
        parent=None,
    ):
        super().__init__(parent)
        self.image_path = image_path
        self.app_manager = app_manager
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
            self.thumbnail_label.setStyleSheet(
                "border: none; background-color: transparent;"
            )

        layout.addWidget(self.thumbnail_label)

        # 3rd: Text display area with rows for filename and caption
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(5, 0, 0, 0)
        text_layout.setSpacing(1)

        # Filename row
        self.name_label = QLabel(self.image_name)
        self.name_label.setStyleSheet(
            "font-size: 12pt; font-weight: bold; color: palette(text);"
        )
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

        # Try to load from QPixmapCache first (in-memory cache for speed)
        cache_key = f"{self.image_path}_{self.thumbnail_size}"
        pixmap = QPixmapCache.find(cache_key)

        if pixmap is None:
            # Try to get from CacheRepository (disk cache) if available - handles both images and videos
            thumbnail_path = None
            if self.app_manager and self.app_manager.cache_repo:
                try:
                    media_hash = self.image_path.stem
                    thumbnail_path = self.app_manager.cache_repo.get_thumbnail(
                        media_hash, self.image_path
                    )
                except Exception as e:
                    print(f"Error getting thumbnail from cache: {e}")
                    thumbnail_path = None

            # Load from thumbnail cache or original file
            if thumbnail_path and thumbnail_path.exists():
                pixmap = QPixmap(str(thumbnail_path))
            else:
                # Fallback: load original image (videos won't work here, but cache should handle them)
                pixmap = QPixmap(str(self.image_path))

            if not pixmap.isNull():
                # Scale to fit within the fixed size while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(
                    self.thumbnail_size,
                    self.thumbnail_size,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                # Cache the scaled thumbnail in memory for future use
                QPixmapCache.insert(cache_key, scaled_pixmap)
                self.thumbnail_label.setPixmap(scaled_pixmap)
                # Center the pixmap in the fixed-size label
                self.thumbnail_label.setAlignment(Qt.AlignCenter)
            else:
                self.thumbnail_label.setText("No Image")
                self.thumbnail_label.setAlignment(Qt.AlignCenter)
        else:
            # Found in memory cache - use it directly
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
        self._loading_default_filter = False  # Prevent infinite recursion
        self._last_toggled_index = -1  # Track last toggled item for shift-select

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

        # Video metadata cache to avoid reopening videos
        self._video_metadata_cache = {}  # {video_path: {duration_str, resolution_str, ...}}

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
        self.app_manager.active_image_changed.connect(self._on_active_image_changed)
        self.app_manager.project_changed.connect(self._update_window_title)
        self.app_manager.library_changed.connect(self._update_window_title)
        self.app_manager.project_changed.connect(self._update_filter_button_appearance)
        self.app_manager.project_changed.connect(self._load_default_filter)

        # Set initial window title and filter button
        self._update_window_title()
        self._update_filter_button_appearance()

        # View selector moved to main window

        # Initial load
        self.refresh()

        # Load default filter if set
        self._load_default_filter()

    def _update_window_title(self):
        """Update window title to show library/project name"""
        library = self.app_manager.get_library()
        project = self.app_manager.get_project()

        # Build title
        title_parts = ["Gallery"]

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

        # View selector moved to main window
        header_layout.addStretch()

        # Action buttons (right side)
        self.filter_btn = QPushButton("Filter")
        self.filter_btn.setToolTip("Filter images by tags")
        self.filter_btn.clicked.connect(self._open_filter_dialog)
        header_layout.addWidget(self.filter_btn)

        self.sort_btn = QPushButton("Sort by Likeness")
        self.sort_btn.setToolTip("Sort images by visual similarity")
        self.sort_btn.clicked.connect(self._open_sort_dialog)
        header_layout.addWidget(self.sort_btn)

        self.sort_repeats_btn = QPushButton("Sort by Repeats")
        self.sort_repeats_btn.setToolTip("Sort images by repeat count (highest first)")
        self.sort_repeats_btn.clicked.connect(self._sort_by_repeats)
        header_layout.addWidget(self.sort_repeats_btn)

        layout.addLayout(header_layout)

        # Tree widget
        self.image_tree = QTreeWidget()
        self.image_tree.setHeaderHidden(True)  # Hide column labels
        self.image_tree.setColumnCount(1)  # Only use first column for content
        self.image_tree.setColumnWidth(0, 600)  # Make main column wider
        self.image_tree.currentItemChanged.connect(self._on_item_changed)
        self.image_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.image_tree.itemExpanded.connect(self._on_item_expanded)
        self.image_tree.itemCollapsed.connect(self._on_item_collapsed)
        # Connect scrollbar to trigger lazy loading of newly visible items
        self.image_tree.verticalScrollBar().valueChanged.connect(self._on_scroll)
        # Install event filter to handle keyboard events
        self.image_tree.installEventFilter(self)

        # Enable custom context menu for right-click
        self.image_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_tree.customContextMenuRequested.connect(self._show_context_menu)

        # Make tree arrows bigger using indentation and icon size
        self.image_tree.setIndentation(
            30
        )  # Double the default indentation (default is ~20)
        self.image_tree.setIconSize(QSize(20, 20))  # Make icons much bigger
        self.image_tree.setExpandsOnDoubleClick(
            False
        )  # We'll handle double click ourselves
        self.image_tree.setRootIsDecorated(
            True
        )  # Show tree arrows for items with children

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
        keyboard_hint = QLabel(
            "Keyboard: ↑↓ navigate • Space toggle select • C clear all • Del remove"
        )
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
            self.status_label.setText(
                f"{count} image{'s' if count != 1 else ''} selected"
            )
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
        self._last_toggled_index = -1  # Reset range selection anchor on refresh

        if current_view is None:
            self.status_label.setText("No library or project loaded")
            self._updating = False
            return

        # Get images from current view (filtered or all)
        images = current_view.get_all_paths()
        self._last_filtered_images = tuple(images)

        # Show loading progress in status
        self.status_label.setText(f"Loading {len(images)} images...")
        self.status_label.setStyleSheet(
            "font-weight: bold; color: #2196F3;"
        )  # Blue color to indicate loading

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

            # Start lazy loading for thumbnails
            if self._lazy_load_enabled:
                self._start_lazy_loading()
            else:
                # If lazy loading is disabled, load all visible thumbnails immediately
                self._load_visible_thumbnails()

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
                if widget and hasattr(widget, "load_thumbnail_if_needed"):
                    widget.load_thumbnail_if_needed()

        # Queue all top-level items for background loading (children will be loaded when visible)
        self._pending_thumbnail_indices = list(
            range(self.image_tree.topLevelItemCount())
        )

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
                        grandchild_rect = self.image_tree.visualItemRect(
                            grandchild_item
                        )

                        if viewport_rect.intersects(grandchild_rect):
                            visible_items.append(grandchild_item)

        return visible_items

    def _load_next_batch(self):
        """Load next batch of thumbnails in background"""
        if not self._pending_thumbnail_indices:
            self._lazy_load_timer.stop()
            return

        # Load next batch
        batch = self._pending_thumbnail_indices[: self._lazy_load_batch_size]
        self._pending_thumbnail_indices = self._pending_thumbnail_indices[
            self._lazy_load_batch_size :
        ]

        for idx in batch:
            if idx < self.image_tree.topLevelItemCount():
                item = self.image_tree.topLevelItem(idx)
                widget = self.image_tree.itemWidget(item, 0)
                if widget and hasattr(widget, "load_thumbnail_if_needed"):
                    widget.load_thumbnail_if_needed()
                # Also check child items (related images)
                for j in range(item.childCount()):
                    child = item.child(j)

                    # Load category item thumbnail if it has one
                    child_widget = self.image_tree.itemWidget(child, 0)
                    if child_widget and hasattr(
                        child_widget, "load_thumbnail_if_needed"
                    ):
                        child_widget.load_thumbnail_if_needed()

                    # Load grandchildren thumbnails (actual related images)
                    for k in range(child.childCount()):
                        grandchild = child.child(k)
                        grandchild_widget = self.image_tree.itemWidget(grandchild, 0)
                        if grandchild_widget and hasattr(
                            grandchild_widget, "load_thumbnail_if_needed"
                        ):
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
            if widget and hasattr(widget, "load_thumbnail_if_needed"):
                widget.load_thumbnail_if_needed()

            # Also check if this is a parent item and load children if expanded
            if item.isExpanded():
                for j in range(item.childCount()):
                    child = item.child(j)
                    child_widget = self.image_tree.itemWidget(child, 0)
                    if child_widget and hasattr(
                        child_widget, "load_thumbnail_if_needed"
                    ):
                        child_widget.load_thumbnail_if_needed()

                    # Load grandchildren if child is expanded
                    if child.isExpanded():
                        for k in range(child.childCount()):
                            grandchild = child.child(k)
                            grandchild_widget = self.image_tree.itemWidget(
                                grandchild, 0
                            )
                            if grandchild_widget and hasattr(
                                grandchild_widget, "load_thumbnail_if_needed"
                            ):
                                grandchild_widget.load_thumbnail_if_needed()

    def _on_active_image_changed(self):
        """Handle active image changes - scroll to and highlight the active image"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        active_image = current_view.get_active()
        if not active_image:
            return

        # Find the item corresponding to the active image
        found = False
        for i in range(self.image_tree.topLevelItemCount()):
            item = self.image_tree.topLevelItem(i)
            if not item:
                continue

            try:
                img_path = item.data(0, Qt.UserRole)
                if img_path == active_image:
                    # Set this item as current (highlights it)
                    self.image_tree.setCurrentItem(item)
                    # Scroll to make it visible (use EnsureVisible for better performance)
                    self.image_tree.scrollToItem(item, QAbstractItemView.EnsureVisible)
                    found = True
                    break
            except RuntimeError:
                # Item was deleted during iteration, skip it
                continue

    def _show_context_menu(self, position):
        """Show context menu for gallery items on right-click"""
        # Get the item at the click position
        item = self.image_tree.itemAt(position)
        if not item:
            return  # Clicked on empty space

        # Check if this is a category item (skip context menu for categories)
        if item.data(0, Qt.UserRole + 1) == "category":
            return

        # Get the image path
        img_path = item.data(0, Qt.UserRole)
        if not img_path:
            return

        # Create context menu
        menu = QMenu(self)

        # Add "Copy Files" action
        copy_files_action = QAction("Copy Files", self)
        copy_files_action.setToolTip("Copy files to clipboard (paste in file manager)")
        copy_files_action.triggered.connect(self._copy_files_to_clipboard)
        menu.addAction(copy_files_action)

        # Add "Copy Paths" action
        copy_paths_action = QAction("Copy Paths", self)
        copy_paths_action.setToolTip("Copy file paths as text")
        copy_paths_action.triggered.connect(self._copy_image_paths)
        menu.addAction(copy_paths_action)

        menu.addSeparator()

        # Add "Open in External App" action
        open_external_action = QAction("Open in External App", self)
        open_external_action.setToolTip("Open with default application (xdg-open)")
        open_external_action.triggered.connect(self._open_in_external_app)
        menu.addAction(open_external_action)

        # Add "Open With..." action
        open_with_action = QAction("Open With...", self)
        open_with_action.setToolTip("Choose application to open with")
        open_with_action.triggered.connect(self._open_with_dialog)
        menu.addAction(open_with_action)

        # Show menu at cursor position (convert widget coordinates to screen coordinates)
        menu.exec_(self.image_tree.viewport().mapToGlobal(position))

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

        # Check if selected images changed - if so, update checkboxes efficiently
        # Avoid loading image data for all items on every selection change for performance
        selected_images = set(current_view.get_selected())

        # Update checkboxes for all visible items (not just first 50)
        # This ensures all selected items show as checked in the UI
        for i in range(self.image_tree.topLevelItemCount()):
            item = self.image_tree.topLevelItem(i)
            widget = self.image_tree.itemWidget(item, 0)
            if widget and hasattr(widget, "checkbox"):
                img_path = item.data(0, Qt.UserRole)

                # Update checkbox state only if it changed
                is_selected = img_path in selected_images
                if widget.checkbox.isChecked() != is_selected:
                    self._updating = True
                    widget.checkbox.setChecked(is_selected)
                    self._updating = False

        # Update status display
        self._update_status_display()

        # Don't force selection synchronization - let user navigate freely
        # The active image is shown in main window, but tree selection stays where user navigates

    def eventFilter(self, obj, event):
        """Handle keyboard events for the tree widget"""
        if obj == self.image_tree and event.type() == QEvent.KeyPress:
            print(f"[GALLERY KEYPRESS] Key event received in gallery")
            key = event.key()
            current_item = self.image_tree.currentItem()

            if key == Qt.Key_Space and current_item:
                # Toggle selection for active image
                widget = self.image_tree.itemWidget(current_item, 0)
                if widget and hasattr(widget, "checkbox"):
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
            if widget and hasattr(widget, "checkbox"):
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
            view_type = (
                "project"
                if self.app_manager.current_view_mode == "project"
                else "library"
            )
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle(f"Remove from {view_type.title()}")

            # Main message
            msg_box.setText(
                f"Remove {count} image{'s' if count != 1 else ''} from the {view_type}?"
            )

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
            removed_count = self.app_manager.remove_images_from_project(
                images_to_delete
            )
        else:
            # Remove from library
            library = self.app_manager.get_library()
            if library and library.library_image_list:
                removed_count = library.library_image_list.remove_images(
                    images_to_delete
                )
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

        # Track the deleted active image for smart next selection
        deleted_active = (
            current_view.get_active()
            if current_view.get_active() in images_to_remove_set
            else None
        )
        deleted_index = None

        # If we need to find the position of deleted image, scan first
        if deleted_active:
            for i in range(self.image_tree.topLevelItemCount()):
                item = self.image_tree.topLevelItem(i)
                if item and item.data(0, Qt.UserRole) == deleted_active:
                    deleted_index = i
                    break

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
        if deleted_active and self.image_tree.topLevelItemCount() > 0:
            # Try to select the next image in the original position
            # If deleted was at index 3, try to select what's now at index 3
            new_item = None

            if deleted_index is not None:
                # Try to select the next image (at the deleted position)
                if deleted_index < self.image_tree.topLevelItemCount():
                    new_item = self.image_tree.topLevelItem(deleted_index)
                # If deleted was the last, go to the previous
                elif self.image_tree.topLevelItemCount() > 0:
                    new_item = self.image_tree.topLevelItem(
                        self.image_tree.topLevelItemCount() - 1
                    )

            # Fallback: just select first item if we couldn't find a good next
            if not new_item:
                new_item = self.image_tree.topLevelItem(0)

            if new_item:
                new_active_path = new_item.data(0, Qt.UserRole)
                current_view.set_active(new_active_path)

                # CRITICAL: Must set _updating = False BEFORE emitting signals
                # so that _on_active_image_changed can run and update the image viewer
                self._updating = False

                # Emit signal to update image viewer and tag editor
                self.app_manager.active_image_changed.emit()

                # Set current item - this will trigger _on_item_changed
                self.image_tree.setCurrentItem(new_item)

                # Manually call selection changed handler to ensure UI updates
                self._on_selection_changed()

                # CRITICAL: Set focus back to the image tree so keyboard events work
                self._restore_focus_after_delete()
                return

        self._updating = False
        self._updating = False

    def _restore_focus_after_delete(self):
        """Restore keyboard focus to the gallery after deleting an image"""

        # Use a timer to restore focus after the event loop has processed signals
        # This ensures other widgets don't steal focus after we set it
        def restore():
            self.image_tree.setFocus(Qt.ActiveWindowFocusReason)

        # Schedule the focus restoration with a very short delay
        QTimer.singleShot(10, restore)

    def _copy_files_to_clipboard(self):
        """Copy selected files to clipboard (actual files, not just paths)"""
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Get images to copy (selected or active)
        images_to_copy = current_view.get_working_images()
        if not images_to_copy:
            QMessageBox.information(self, "No Selection", "No images to copy.")
            return

        # Create QMimeData with file URLs
        mime_data = QMimeData()
        urls = [
            QUrl.fromLocalFile(str(img_path.resolve())) for img_path in images_to_copy
        ]
        mime_data.setUrls(urls)

        # GNOME/Nautilus specific: Add x-special/gnome-copied-files format
        # Format: "copy\n" followed by file:// URLs (one per line)
        gnome_data = "copy\n" + "\n".join([url.toString() for url in urls])
        mime_data.setData("x-special/gnome-copied-files", gnome_data.encode())

        # KDE/Dolphin uses standard text/uri-list (automatically set by setUrls())

        # Set to clipboard
        from PyQt5.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        clipboard.setMimeData(mime_data)

        QMessageBox.information(
            self,
            "Files Copied",
            f"Copied {len(images_to_copy)} file(s) to clipboard.\n\n"
            "You can now paste them in your file manager.",
        )

    def _open_in_external_app(self):
        """Open selected images in external application using xdg-open"""
        import subprocess

        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Get images to open (selected or active)
        images_to_open = current_view.get_working_images()
        if not images_to_open:
            QMessageBox.information(self, "No Selection", "No images to open.")
            return

        # Open each file with xdg-open
        opened_count = 0
        failed_files = []
        for img_path in images_to_open:
            try:
                # Use Popen to launch in background (non-blocking)
                subprocess.Popen(["xdg-open", str(img_path.resolve())])
                opened_count += 1
            except FileNotFoundError:
                QMessageBox.warning(
                    self,
                    "Error",
                    "xdg-open not found. Please install xdg-utils package.",
                )
                return
            except Exception as e:
                failed_files.append(f"{img_path.name}: {str(e)}")

        # Show results
        if failed_files:
            QMessageBox.warning(
                self,
                "Partially Opened",
                f"Opened {opened_count} file(s), but {len(failed_files)} failed:\n\n"
                + "\n".join(failed_files[:5]),  # Show first 5 errors
            )
        elif opened_count == 1:
            # Don't show confirmation for single file (less intrusive)
            pass
        else:
            QMessageBox.information(
                self,
                "Files Opened",
                f"Opened {opened_count} file(s) in external application(s).",
            )

    def _open_with_dialog(self):
        """Open selected files using GTK AppChooser dialog to pick application"""
        import os

        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Get images to open (selected or active)
        images_to_open = current_view.get_working_images()
        if not images_to_open:
            QMessageBox.information(self, "No Selection", "No images to open.")
            return

        # Try to import GTK
        try:
            import gi

            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, Gio
        except ImportError:
            QMessageBox.warning(
                self,
                "GTK Not Available",
                "The 'Open With...' feature requires python3-gi to be installed.\n\n"
                "Install it with:\n"
                "  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-3.0\n"
                "  Fedora: sudo dnf install python3-gobject gtk3\n"
                "  Arch: sudo pacman -S python-gobject gtk3",
            )
            return
        except ValueError as e:
            QMessageBox.warning(
                self,
                "GTK Version Error",
                f"Could not load GTK 3.0: {str(e)}\n\n"
                "Make sure gir1.2-gtk-3.0 is installed.",
            )
            return

        # Process each file
        opened_count = 0
        for img_path in images_to_open:
            try:
                # Create Gio file object
                gfile = Gio.File.new_for_path(str(img_path.resolve()))

                # Get file MIME type
                file_info = gfile.query_info(
                    "standard::content-type", Gio.FileQueryInfoFlags.NONE, None
                )
                content_type = file_info.get_content_type()

                # Create GTK AppChooser dialog
                dialog = Gtk.AppChooserDialog.new_for_content_type(
                    None, Gtk.DialogFlags.MODAL, content_type
                )
                dialog.set_title(f"Open {img_path.name} With...")

                # Show dialog and get response
                response = dialog.run()

                if response == Gtk.ResponseType.OK:
                    app_info = dialog.get_app_info()
                    if app_info:
                        try:
                            # Launch the application with the file
                            app_info.launch([gfile], None)
                            opened_count += 1
                        except Exception as e:
                            QMessageBox.warning(
                                self,
                                "Launch Error",
                                f"Failed to launch {app_info.get_display_name()}:\n{str(e)}",
                            )

                # Destroy dialog
                dialog.destroy()

                # Process GTK events to clean up
                while Gtk.events_pending():
                    Gtk.main_iteration()

                # If user cancelled, don't process remaining files
                if response != Gtk.ResponseType.OK:
                    break

            except Exception as e:
                QMessageBox.warning(
                    self, "Error", f"Failed to open {img_path.name}:\n{str(e)}"
                )
                break

        # Show summary for multiple files
        if opened_count > 1:
            QMessageBox.information(
                self,
                "Files Opened",
                f"Opened {opened_count} file(s) with selected application(s).",
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
            "You can now paste these paths into the Import dialog.",
        )

    # Source selector methods removed - functionality moved to view selector

    def _on_checkbox_clicked(self, img_path: Path, state: int):
        """Handle checkbox click - toggle image selection"""
        if self._updating:
            return

        current_view = self.app_manager.get_current_view()
        if current_view is None:
            return

        # Check for Shift modifier for range selection
        modifiers = QApplication.keyboardModifiers()
        is_shift = modifiers & Qt.ShiftModifier

        # Find current index in the tree
        current_index = -1
        for i in range(self.image_tree.topLevelItemCount()):
            item = self.image_tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == img_path:
                current_index = i
                break

        if current_index == -1:
            return

        # Handle range selection
        if is_shift and self._last_toggled_index != -1:
            start = min(self._last_toggled_index, current_index)
            end = max(self._last_toggled_index, current_index)
            target_state = state == Qt.Checked

            # Prevent recursive updates
            self._updating = True

            try:
                for i in range(start, end + 1):
                    item = self.image_tree.topLevelItem(i)
                    path = item.data(0, Qt.UserRole)

                    # Update model
                    if target_state:
                        current_view.select(path)
                    else:
                        current_view.deselect(path)

                    # Update widget UI immediately
                    widget = self.image_tree.itemWidget(item, 0)
                    if widget and hasattr(widget, "checkbox"):
                        widget.checkbox.setChecked(target_state)
            finally:
                self._updating = False

            # Emit change signal once
            self.app_manager.update_project(save=False)

        else:
            # Normal single selection
            if state == Qt.Checked:
                current_view.select(img_path)
            else:
                current_view.deselect(img_path)

            # Emit selection changed to update UI
            self.app_manager.update_project(save=False)

        # Update last toggled index
        self._last_toggled_index = current_index

    def _on_item_changed(
        self, current_item: "QTreeWidgetItem", previous_item: "QTreeWidgetItem"
    ):
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

    def _on_item_double_clicked(self, item: "QTreeWidgetItem", column: int):
        """Handle double-click on tree items - toggle expansion"""
        if item and item.childCount() > 0:
            # Only toggle expansion for items that have children
            item.setExpanded(not item.isExpanded())
            # If we expanded an item, trigger thumbnail loading for its children
            if item.isExpanded():
                self._load_children_thumbnails(item)

    def _load_children_thumbnails(self, parent_item: "QTreeWidgetItem"):
        """Load thumbnails for all children and grandchildren of an item"""
        for j in range(parent_item.childCount()):
            child = parent_item.child(j)
            child_widget = self.image_tree.itemWidget(child, 0)
            if child_widget and hasattr(child_widget, "load_thumbnail_if_needed"):
                child_widget.load_thumbnail_if_needed()

            # Load grandchildren if child has them
            for k in range(child.childCount()):
                grandchild = child.child(k)
                grandchild_widget = self.image_tree.itemWidget(grandchild, 0)
                if grandchild_widget and hasattr(
                    grandchild_widget, "load_thumbnail_if_needed"
                ):
                    grandchild_widget.load_thumbnail_if_needed()

    def _on_item_expanded(self, item: "QTreeWidgetItem"):
        """Handle tree item expansion - load thumbnails for newly visible items"""
        self._load_children_thumbnails(item)

    def _on_item_collapsed(self, item: "QTreeWidgetItem"):
        """Handle tree item collapse - no special action needed"""
        pass

    def _load_visible_thumbnails(self):
        """Load thumbnails for all currently visible items in the tree"""
        from PyQt5.QtWidgets import QApplication

        QApplication.processEvents()  # Ensure the tree is fully rendered

        # Get all visible items
        visible_items = self._get_visible_items()

        # Load thumbnails for visible items
        for item in visible_items:
            widget = self.image_tree.itemWidget(item, 0)
            if widget and hasattr(widget, "load_thumbnail_if_needed"):
                widget.load_thumbnail_if_needed()

        # Also load thumbnails for items that will be visible with minimal scrolling
        # This improves user experience by pre-loading nearby thumbnails
        viewport = self.image_tree.viewport()
        viewport_height = viewport.height()
        preload_margin = viewport_height  # Load one extra screen height worth

        for i in range(self.image_tree.topLevelItemCount()):
            item = self.image_tree.topLevelItem(i)
            rect = self.image_tree.visualItemRect(item)
            # Include items that are just outside the viewport (within preload margin)
            if (
                rect.top() < viewport_height + preload_margin
                and rect.bottom() > -preload_margin
            ):
                widget = self.image_tree.itemWidget(item, 0)
                if widget and hasattr(widget, "load_thumbnail_if_needed"):
                    widget.load_thumbnail_if_needed()

                # Check children
                for j in range(item.childCount()):
                    child = item.child(j)
                    child_rect = self.image_tree.visualItemRect(child)
                    if (
                        child_rect.top() < viewport_height + preload_margin
                        and child_rect.bottom() > -preload_margin
                    ):
                        child_widget = self.image_tree.itemWidget(child, 0)
                        if child_widget and hasattr(
                            child_widget, "load_thumbnail_if_needed"
                        ):
                            child_widget.load_thumbnail_if_needed()

    def _get_video_info(self, video_path: Path) -> dict:
        """Extract video metadata (duration, resolution) - cached"""
        # Check cache first
        if video_path in self._video_metadata_cache:
            return self._video_metadata_cache[video_path]

        try:
            import cv2
        except ImportError:
            return {}

        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return {}

            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

            # Calculate duration
            duration_seconds = 0
            if fps > 0:
                duration_seconds = frame_count / fps

            # Format duration as MM:SS or H:MM:SS
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            seconds = int(duration_seconds % 60)

            if hours > 0:
                duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                duration_str = f"{minutes}:{seconds:02d}"

            # Format resolution
            resolution_str = f"{width}x{height}"

            result = {
                "duration": duration_seconds,
                "duration_str": duration_str,
                "width": width,
                "height": height,
                "resolution_str": resolution_str,
                "fps": fps,
            }

            # Cache the result
            self._video_metadata_cache[video_path] = result

            return result
        except Exception as e:
            print(f"Error getting video info: {e}")
            return {}

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
                img_name = img_data.get_display_name() if img_data else img_path.stem
                img_caption = img_data.caption if img_data.caption else ""

                # Add repeat count to image name if set
                image_list = self.app_manager.get_image_list()
                if image_list:
                    repeat_count = image_list.get_repeat(img_path)
                    if repeat_count is not None and repeat_count >= 0:
                        img_name = f"{img_name} [{repeat_count}x]"

                # Add video metadata to caption if this is a video
                video_extensions = {
                    ".mp4",
                    ".avi",
                    ".mov",
                    ".mkv",
                    ".webm",
                    ".flv",
                    ".wmv",
                    ".m4v",
                }
                if img_path.suffix.lower() in video_extensions:
                    video_info = self._get_video_info(img_path)
                    if video_info:
                        duration_str = video_info.get("duration_str", "")
                        resolution_str = video_info.get("resolution_str", "")
                        video_caption_parts = []
                        if duration_str:
                            video_caption_parts.append(f"Duration: {duration_str}")
                        if resolution_str:
                            video_caption_parts.append(f"Resolution: {resolution_str}")

                        if video_caption_parts:
                            video_metadata = " | ".join(video_caption_parts)
                            if img_caption:
                                img_caption = f"{img_caption} | {video_metadata}"
                            else:
                                img_caption = video_metadata

                # Create tree item (flat structure - no children)
                main_item = QTreeWidgetItem(self.image_tree)
                main_item.setData(0, Qt.UserRole, img_path)

                # Create widget for item (avoid recaching by using existing data)
                widget = GalleryTreeItemWidget(
                    img_path,
                    img_name,
                    img_caption,
                    self.size_slider.value(),
                    lazy_load=self._lazy_load_enabled,
                    app_manager=self.app_manager,
                )

                # Connect checkbox
                widget.checkbox.stateChanged.connect(
                    lambda state, path=img_path: self._on_checkbox_clicked(path, state)
                )

                self.image_tree.setItemWidget(main_item, 0, widget)

                processed_count += 1

                # Update status periodically
                if (
                    processed_count % update_interval == 0
                    or processed_count == total_images
                ):
                    progress = (processed_count / total_images) * 100
                    self.status_label.setText(
                        f"Loading: {processed_count}/{total_images} ({progress:.0f}%)"
                    )
                    self.status_label.setStyleSheet(
                        "font-weight: bold; color: #2196F3;"
                    )  # Blue during loading
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
        if (
            library
            and library.library_image_list
            and img_path in library.library_image_list.get_all_paths()
        ):
            return "Library"

        # Check projects
        if library:
            for project_name in library.list_projects():
                project_file = library.get_project_file(project_name)
                if project_file and project_file.exists():
                    from .data_models import ProjectData

                    project = ProjectData.load(
                        project_file, library.get_images_directory()
                    )
                    if img_path in project.image_list.get_all_paths():
                        return f"Project: {project_name}"

        return "Unknown"

    # View selector methods (moved from main window)
    # View selector methods moved to main window

    # Filter management methods
    def _load_default_filter(self):
        """Load and apply default image filter if set"""
        # Prevent infinite recursion
        if hasattr(self, "_loading_default_filter") and self._loading_default_filter:
            return

        self._loading_default_filter = True

        try:
            # Load filter from library or project depending on view mode
            if self.app_manager.current_view_mode == "library":
                library = self.app_manager.get_library()
                if not library:
                    return
                filters_dict = library.filters
            else:
                project = self.app_manager.get_project()
                if not project:
                    return
                filters_dict = project.filters

            # Use image-specific default filter key
            default_filter = filters_dict.get("image_default_filter", "")
            print(f"[DEBUG] Gallery loading default filter: {default_filter}")

            if default_filter:
                # Apply the default filter to images
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
                        result = evaluate_filter(default_filter, img_tag_strs)

                        if result:
                            filtered.append(img_path)
                    except Exception as e:
                        print(f"ERROR: Error filtering image {img_path}: {e}")
                        continue

                # Create filtered view
                from .data_models import ImageList

                base_dir = image_list._base_dir
                if base_dir and filtered:
                    filtered_view = ImageList.create_filtered(base_dir, filtered)
                    self.app_manager.set_filtered_view(filtered_view)
                    self.app_manager.current_filter_expression = default_filter
                    print(
                        f"[DEBUG] Applied default filter, {len(filtered)} images match"
                    )
        finally:
            self._loading_default_filter = False

    def _open_filter_dialog(self):
        """Open the filter dialog"""
        from .saved_filters_dialog import SavedFiltersDialog

        # Pass current filter expression to dialog
        current_filter = self.app_manager.current_filter_expression
        dialog = SavedFiltersDialog(
            self.app_manager, parent=self, current_filter=current_filter
        )
        dialog.exec_()

        # Update button appearance after dialog closes
        self._update_filter_button_appearance()

    def _update_filter_button_appearance(self):
        """Update filter button appearance based on whether filter is active"""
        if self.app_manager.filtered_view is not None:
            # Filter is active - make button stand out with black text on white background
            self.filter_btn.setStyleSheet(
                "QPushButton { font-weight: bold; background-color: white; color: black; }"
            )
            self.filter_btn.setText("Filter ✓")
        else:
            # No filter active - normal appearance
            self.filter_btn.setStyleSheet("")
            self.filter_btn.setText("Filter")

    # Placeholder methods for new functionality
    def _open_sort_dialog(self):
        """Open the Sort by Likeness dialog using pHash clustering with live updates"""
        # Always work with the base image list (project or library), not filtered views
        base_image_list = self.app_manager.get_image_list()
        if base_image_list is None:
            QMessageBox.warning(
                self, "No View", "Please select a view (library or project) first."
            )
            return

        images = base_image_list.get_all_paths()

        if not images:
            QMessageBox.information(
                self, "No Images", "No images to sort in the current view."
            )
            return

        # Create sort dialog
        from PyQt5.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QHBoxLayout,
            QLabel,
            QSlider,
            QPushButton,
            QDialogButtonBox,
            QProgressBar,
            QTextEdit,
            QGroupBox,
            QComboBox,
            QApplication,
        )
        from PyQt5.QtCore import QTimer
        from PIL import Image
        import imagehash
        from sklearn.cluster import AgglomerativeClustering
        from scipy.spatial.distance import pdist, squareform
        import numpy as np
        from datetime import datetime

        dialog = QDialog(self)
        dialog.setWindowTitle("Sort by Likeness (Image Hash Clustering)")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)

        layout = QVBoxLayout(dialog)

        # Get library for hash storage
        library = self.app_manager.get_library()
        if not library:
            QMessageBox.warning(self, "No Library", "No library loaded.")
            return

        # Load saved settings
        saved_settings = library.metadata.get("sort_by_likeness_settings", {})
        default_threshold = saved_settings.get("threshold", 6)
        default_algorithm = saved_settings.get("algorithm", "Perceptual Hash (pHash)")
        default_linkage = saved_settings.get("linkage", "average")

        # Clustering parameters
        cluster_group = QGroupBox("Clustering Parameters")
        cluster_group.setEnabled(False)  # Initially disabled until hashes are loaded
        cluster_layout = QVBoxLayout(cluster_group)

        # Distance threshold slider
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("Distance Threshold:"))
        threshold_label = QLabel(str(default_threshold))
        threshold_label.setAlignment(Qt.AlignCenter)
        threshold_layout.addWidget(threshold_label)
        cluster_layout.addLayout(threshold_layout)

        threshold_slider = QSlider(Qt.Horizontal)
        threshold_slider.setMinimum(1)
        threshold_slider.setMaximum(25)
        threshold_slider.setValue(default_threshold)
        threshold_slider.valueChanged.connect(lambda v: threshold_label.setText(str(v)))
        cluster_layout.addWidget(threshold_slider)

        # Hash algorithm selection
        algo_layout = QHBoxLayout()
        algo_layout.addWidget(QLabel("Hash Algorithm:"))
        algo_combo = QComboBox()
        algo_combo.addItems(
            [
                "Perceptual Hash (pHash)",
                "Difference Hash (dHash)",
                "Average Hash",
                "Wavelet Hash",
            ]
        )
        algo_combo.setCurrentText(default_algorithm)
        algo_layout.addWidget(algo_combo)
        cluster_layout.addLayout(algo_layout)

        # Linkage method selection
        linkage_layout = QHBoxLayout()
        linkage_layout.addWidget(QLabel("Linkage Method:"))
        linkage_combo = QComboBox()
        linkage_combo.addItems(["average", "complete", "single"])
        linkage_combo.setCurrentText(default_linkage)
        linkage_layout.addWidget(linkage_combo)
        cluster_layout.addLayout(linkage_layout)

        # Info label
        info_label = QLabel(
            "Lower threshold = More clusters ( stricter similarity )\nHigher threshold = Fewer clusters ( looser similarity )"
        )
        info_label.setStyleSheet("color: gray; font-size: 10px;")
        cluster_layout.addWidget(info_label)

        layout.addWidget(cluster_group)

        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setVisible(False)
        layout.addWidget(progress_bar)

        # Status text area
        status_text = QTextEdit()
        status_text.setReadOnly(True)
        status_text.setMaximumHeight(150)
        status_text.append("⏳ Initializing... Please wait.")
        layout.addWidget(status_text)

        # Global variables for live clustering
        image_hashes = []
        valid_images = []
        hash_algorithm = default_algorithm
        clustering_timer = QTimer()
        clustering_timer.setSingleShot(True)

        def get_hash_function(algo_text):
            """Get hash function based on algorithm selection"""
            if "pHash" in algo_text:
                return imagehash.phash, "phash"
            elif "dHash" in algo_text:
                return imagehash.dhash, "dhash"
            elif "Average" in algo_text:
                return imagehash.average_hash, "average_hash"
            elif "Wavelet" in algo_text:
                return imagehash.whash, "whash"
            else:
                return imagehash.phash, "phash"

        def load_or_calculate_hashes():
            """Load cached hashes or calculate new ones"""
            nonlocal image_hashes, valid_images, hash_algorithm

            hash_func, algo_key = get_hash_function(algo_combo.currentText())
            hash_algorithm = algo_combo.currentText()

            # Check for cached hashes
            cached_hashes = library.metadata.get("image_hashes", {})
            cached_algo = cached_hashes.get("algorithm")
            cached_hash_data = cached_hashes.get("hashes", {})

            status_text.clear()
            status_text.append(f"🔍 Checking for cached {hash_algorithm} hashes...")

            # Check if we have valid cached hashes for this algorithm
            missing_hashes = []
            valid_cached_hashes = {}

            for img_path in images:
                img_hash = img_path.stem  # filename without extension is the hash
                if img_hash in cached_hash_data and cached_algo == algo_key:
                    try:
                        # Convert cached string back to int
                        hash_int = int(cached_hash_data[img_hash], 16)
                        valid_cached_hashes[img_hash] = hash_int
                    except (ValueError, TypeError):
                        missing_hashes.append(img_path)
                else:
                    missing_hashes.append(img_path)

            # Load cached hashes
            image_hashes = []
            valid_images = []
            for img_path in images:
                img_hash = img_path.stem
                if img_hash in valid_cached_hashes:
                    image_hashes.append(valid_cached_hashes[img_hash])
                    valid_images.append(img_path)

            cached_count = len(valid_images)
            total_count = len(images)

            if cached_count == total_count:
                status_text.append(f"✅ Loaded all {cached_count} hashes from cache")
                return True
            else:
                status_text.append(
                    f"📦 Loaded {cached_count}/{total_count} hashes from cache"
                )
                status_text.append(
                    f"🔧 Calculating {len(missing_hashes)} missing hashes..."
                )

                # Calculate missing hashes
                progress_bar.setVisible(True)
                progress_bar.setMaximum(len(missing_hashes))
                errors = []

                for idx, img_path in enumerate(missing_hashes):
                    try:
                        if not img_path.exists() or not img_path.is_file():
                            errors.append(f"File not found: {img_path.name}")
                            continue

                        img = Image.open(img_path)
                        if img.mode not in ["RGB", "L"]:
                            img = img.convert("RGB")

                        hash_value = hash_func(img)
                        hash_str = str(hash_value)
                        hash_int = int(hash_str, 16)

                        image_hashes.append(hash_int)
                        valid_images.append(img_path)

                        # Cache the hash
                        img_hash = img_path.stem
                        cached_hash_data[img_hash] = hash_str

                    except Exception as e:
                        errors.append(f"Error processing {img_path.name}: {str(e)}")

                    progress_bar.setValue(idx + 1)
                    from PyQt5.QtWidgets import QApplication

                    QApplication.processEvents()

                # Save updated cache
                library.metadata["image_hashes"] = {
                    "algorithm": algo_key,
                    "hashes": cached_hash_data,
                    "last_updated": str(datetime.now()),
                }
                if hasattr(library, "save"):
                    library.save()
                else:
                    print("Warning: Library object does not have save method")

                progress_bar.setVisible(False)

                if errors:
                    error_msg = (
                        f"⚠️ {len(errors)} images failed hash calculation:\n"
                        + "\n".join(errors[:5])
                    )
                    if len(errors) > 5:
                        error_msg += f"\n... and {len(errors) - 5} more"
                    QMessageBox.warning(dialog, "Hash Calculation Warnings", error_msg)

                status_text.append(
                    f"✅ Hash calculation complete. {len(valid_images)}/{total_count} images processed"
                )
                return len(valid_images) > 0

        def perform_clustering():
            """Perform clustering with current parameters"""
            if not image_hashes or not valid_images:
                return

            distance_threshold = threshold_slider.value()
            linkage_method = linkage_combo.currentText()

            try:
                # Calculate pairwise Hamming distances
                def hamming_distance(x, y):
                    return bin(int(x) ^ int(y)).count("1")

                def hamming_distance_pdist(x):
                    distances = []
                    n = len(x)
                    for i in range(n):
                        for j in range(i + 1, n):
                            dist = hamming_distance(x[i], x[j])
                            distances.append(dist)
                    return np.array(distances)

                distance_vector = hamming_distance_pdist(np.array(image_hashes))

                # Perform clustering
                clustering = AgglomerativeClustering(
                    n_clusters=None,
                    distance_threshold=distance_threshold,
                    metric="precomputed",
                    linkage=linkage_method,
                )

                distance_matrix = squareform(distance_vector)
                cluster_labels = clustering.fit_predict(distance_matrix)

                # Group images by cluster
                clusters = {}
                for img_path, label in zip(valid_images, cluster_labels):
                    if label not in clusters:
                        clusters[label] = []
                    clusters[label].append(img_path)

                # Sort clusters by size (largest first) and by cluster label
                sorted_clusters = sorted(
                    clusters.items(), key=lambda x: (-len(x[1]), x[0])
                )

                # Create final sorted list
                sorted_images = []
                for cluster_id, cluster_images in sorted_clusters:
                    sorted_images.extend(cluster_images)

                print(f"DEBUG: Clustering produced {len(sorted_images)} sorted images")
                if sorted_images:
                    print(
                        f"DEBUG: First few sorted images: {[str(p.name) for p in sorted_images[:3]]}"
                    )

                # Apply sorting to gallery
                n_clusters = len(sorted_clusters)
                status_text.append(
                    f"🎯 Applied clustering: {n_clusters} clusters, threshold={distance_threshold}"
                )
                self._apply_sorted_order_to_view(sorted_images)

            except Exception as e:
                status_text.append(f"❌ Clustering error: {str(e)}")

        def on_parameter_changed():
            """Handle parameter changes - debounce clustering"""
            clustering_timer.stop()
            clustering_timer.start(500)  # 500ms delay

        def on_algorithm_changed():
            """Handle algorithm changes - reload hashes and cluster"""
            if load_or_calculate_hashes():
                perform_clustering()

        def apply_sorting():
            """Apply current sorting and save settings"""
            # Save current settings
            current_settings = {
                "threshold": threshold_slider.value(),
                "algorithm": algo_combo.currentText(),
                "linkage": linkage_combo.currentText(),
            }
            library.metadata["sort_by_likeness_settings"] = current_settings
            if hasattr(library, "save"):
                library.save()
            else:
                print("Warning: Library object does not have save method")

            # Perform final clustering
            perform_clustering()
            dialog.accept()

        def clear_sorting():
            """Clear sorting and revert to default order"""
            success = self._apply_sorted_order_to_view(images)  # Original order
            if success:
                status_text.append("✅ Cleared sorting - reverted to default order")
            else:
                status_text.append("❌ Failed to clear sorting")

        # Show dialog immediately, then start hash calculation
        dialog.show()

        # Start hash calculation asynchronously
        from PyQt5.QtCore import QTimer

        hash_timer = QTimer()
        hash_timer.setSingleShot(True)
        hash_timer.timeout.connect(lambda: start_hash_calculation())
        hash_timer.start(100)  # Small delay to ensure dialog is visible

        def start_hash_calculation():
            """Start the hash calculation process"""
            status_text.append("🔍 Checking for cached hashes...")
            QApplication.processEvents()  # Keep UI responsive

            if not load_or_calculate_hashes():
                QMessageBox.warning(
                    dialog,
                    "No Valid Images",
                    "No images could be processed for hashing.",
                )
                dialog.reject()
                return

            # Enable controls and connect handlers now that hashes are loaded
            cluster_group.setEnabled(True)
            clear_btn.setEnabled(True)
            apply_btn.setEnabled(True)
            status_text.append(
                "✅ Ready for clustering! Adjust parameters to see live results."
            )

            # Connect parameter change handlers
            threshold_slider.valueChanged.connect(on_parameter_changed)
            algo_combo.currentTextChanged.connect(on_algorithm_changed)
            linkage_combo.currentTextChanged.connect(on_parameter_changed)
            clustering_timer.timeout.connect(perform_clustering)

            # Perform initial clustering
            perform_clustering()

        # Perform initial clustering
        perform_clustering()

        # Dialog buttons
        button_layout = QHBoxLayout()

        clear_btn = QPushButton("Clear Sorting")
        clear_btn.setToolTip("Revert to default image order")
        clear_btn.setEnabled(False)  # Initially disabled
        clear_btn.clicked.connect(clear_sorting)
        button_layout.addWidget(clear_btn)

        button_layout.addStretch()

        apply_btn = QPushButton("Apply & Close")
        apply_btn.setToolTip("Apply current sorting and close dialog")
        apply_btn.setEnabled(False)  # Initially disabled
        apply_btn.clicked.connect(apply_sorting)
        button_layout.addWidget(apply_btn)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        button_layout.addWidget(button_box)

        layout.addLayout(button_layout)

        # Show dialog
        dialog.exec_()

    def _sort_by_repeats(self):
        """Sort images by repeat count (highest first)"""
        # Get current image list
        image_list = self.app_manager.get_image_list()
        if image_list is None:
            QMessageBox.warning(
                self, "No View", "Please select a view (library or project) first."
            )
            return

        # Get all images with their repeat counts
        all_images = image_list.get_all_paths()
        if not all_images:
            QMessageBox.information(self, "No Images", "No images to sort.")
            return

        # Sort by repeat count (highest first), maintaining original order for ties
        sorted_images = sorted(
            all_images, key=lambda img: image_list.get_repeat(img) or 0, reverse=True
        )

        # Apply the sorted order
        success = self._apply_sorted_order_to_view(sorted_images)
        if success:
            QMessageBox.information(
                self, "Sorted", "Images sorted by repeat count (highest first)"
            )
        else:
            QMessageBox.warning(self, "Error", "Failed to apply sorting")

    def _apply_sorted_order_to_view(self, sorted_images: List[Path]) -> bool:
        """Apply the sorted image order to the base image list (project or library)"""
        try:
            # Always work with the base image list, not filtered views
            base_image_list = self.app_manager.get_image_list()
            if base_image_list is None:
                print("❌ No base image list")
                return False

            # Apply sorting to the base image list
            success = base_image_list.set_order(sorted_images)
            if success:
                # Clear any active filtered view so the sorted base list is shown
                self.app_manager.set_filtered_view(None)

                # Mark as modified
                if self.app_manager.current_view_mode == "project":
                    self.app_manager.pending_changes.mark_project_modified()
                else:
                    self.app_manager.pending_changes.mark_library_modified()

                # Refresh gallery to show new order
                self.refresh()
            return success

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
            QMessageBox.information(
                self, "No Images", "Please select images to add to a project."
            )
            return

        # Get available projects
        library = self.app_manager.get_library()
        if not library:
            QMessageBox.warning(
                self, "No Library", "No library is loaded. Please load a library first."
            )
            return

        projects = library.list_projects()
        if not projects:
            QMessageBox.warning(
                self, "No Projects", "No projects found. Please create a project first."
            )
            return

        # Create project selection dialog
        from PyQt5.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QPushButton,
            QDialogButtonBox,
        )

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
        project_file = library.get_project_file(project_name)
        if not project_file or not project_file.exists():
            QMessageBox.warning(
                self, "Error", f"Could not find project file: {project_name}"
            )
            return

        # Load the project data
        from .data_models import ProjectData

        project = ProjectData.load(project_file, library.get_images_directory())
        if not project:
            QMessageBox.warning(
                self, "Error", f"Could not load project: {project_name}"
            )
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

        # Update project and switch to it if images were added
        if added_count > 0:
            # The project is already loaded with the correct project_file path
            # Just call save() without parameters
            project.save()

            # Switch to the project to show the changes
            self.app_manager.switch_to_project_view(project_name)

            # Refresh gallery to show updated view
            self.refresh()

        # Show result
        if added_count > 0:
            message = f"Added {added_count} image{'s' if added_count != 1 else ''} to project '{project_name}'"
            if already_in_project > 0:
                message += f"\n({already_in_project} image{'s' if already_in_project != 1 else ''} were already in the project)"
            message += f"\n\nSwitched to project '{project_name}' to show the changes."
            QMessageBox.information(self, "Added to Project", message)
        else:
            QMessageBox.information(
                self,
                "No Changes",
                f"All selected images were already in project '{project_name}'",
            )
