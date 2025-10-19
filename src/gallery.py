"""
Gallery - Grid/List view of project images with thumbnails and selection
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QSlider, QCheckBox, QMessageBox
)
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QPixmap, QIcon
from pathlib import Path


class GalleryItemWidget(QWidget):
    """Custom widget for gallery items with thumbnail and checkbox"""

    def __init__(self, image_path: Path, image_name: str, thumbnail_size: int, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setup_ui(image_name, thumbnail_size)

    def setup_ui(self, image_name: str, thumbnail_size: int):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        # Checkbox
        self.checkbox = QCheckBox()
        layout.addWidget(self.checkbox)

        # Thumbnail
        self.thumbnail_label = QLabel()
        pixmap = QPixmap(str(self.image_path))
        if not pixmap.isNull():
            pixmap = pixmap.scaled(thumbnail_size, thumbnail_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumbnail_label.setPixmap(pixmap)
        else:
            self.thumbnail_label.setText("[No Image]")
        layout.addWidget(self.thumbnail_label)

        # Name
        name_label = QLabel(image_name)
        layout.addWidget(name_label)
        layout.addStretch()


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

        # Timer for debouncing thumbnail resize
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._apply_resize)

        self._setup_ui()

        # Connect to signals
        self.app_manager.project_changed.connect(self.refresh)
        self.app_manager.project_changed.connect(self._on_selection_changed)

        # Initial load
        self.refresh()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)

        # Info label
        self.info_label = QLabel("Gallery - Select images")
        layout.addWidget(self.info_label)

        # List widget
        self.image_list = QListWidget()
        self.image_list.currentRowChanged.connect(self._on_row_changed)
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

    def refresh(self):
        """Refresh list from project"""
        if self._updating:
            print("DEBUG Gallery.refresh(): Skipping - already updating")
            return

        print("\n=== GALLERY REFRESH DEBUG ===")
        self._updating = True

        project = self.app_manager.get_project()
        current_view = self.app_manager.get_current_view()

        print(f"Project: {project.project_name if project.project_file else 'None'}")
        print(f"Current view type: {type(current_view).__name__ if current_view is not None else 'None'}")
        print(f"Filtered view: {self.app_manager.filtered_view is not None}")

        # Clear list
        self.image_list.clear()

        if not project.project_file or current_view is None:
            self.info_label.setText("No project loaded")
            self._updating = False
            return

        # Get images from current view (filtered or all)
        images = current_view.get_all_paths()
        self._last_filtered_images = tuple(images)

        print(f"Images in current view: {len(images)}")
        print(f"Image names: {[p.name for p in images]}")
        print("=" * 50 + "\n")

        self.info_label.setText(f"Gallery: {len(images)} images")

        # Get thumbnail size
        thumbnail_size = self.size_slider.value()

        # Populate list
        for img_path in images:
            # Load image data to get name
            img_data = self.app_manager.load_image_data(img_path)
            img_name = img_data.name if img_data.name else img_path.stem

            # Create list item
            item = QListWidgetItem()
            item.setData(Qt.UserRole, img_path)  # Store image path in item
            self.image_list.addItem(item)

            # Create custom widget
            widget = GalleryItemWidget(img_path, img_name, thumbnail_size)

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

    def keyPressEvent(self, event):
        """Handle keyboard events"""
        current_row = self.image_list.currentRow()
        item = self.image_list.item(current_row)

        if event.key() == Qt.Key_Space and item:
            # Toggle selection for active image
            widget = self.image_list.itemWidget(item)
            if widget and hasattr(widget, 'checkbox'):
                widget.checkbox.setChecked(not widget.checkbox.isChecked())
        elif event.key() == Qt.Key_C:
            # Clear selection
            self._remove_all()
        elif event.key() == Qt.Key_Delete:
            # Remove images from project
            self._delete_images()
        else:
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

        # Show confirmation dialog
        count = len(images_to_delete)
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

        if result == QMessageBox.Ok:
            # Remove images
            removed_count = self.app_manager.remove_images_from_project(images_to_delete)

            # Notify changes
            self.app_manager.update_project()
