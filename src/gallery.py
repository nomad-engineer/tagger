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
        self.app_manager.selection_changed.connect(self._on_selection_changed)

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
            return

        self._updating = True

        project = self.app_manager.get_project()
        selection = self.app_manager.get_selection()

        # Clear list
        self.image_list.clear()

        if not project.project_file:
            self.info_label.setText("No project loaded")
            self._updating = False
            return

        # Get filtered images (or all if no filter)
        images = selection.filtered_images if selection.filtered_images is not None else project.get_all_absolute_image_paths()
        self._last_filtered_images = tuple(selection.filtered_images) if selection.filtered_images is not None else None
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
            widget.checkbox.stateChanged.connect(lambda state, path=img_path: self._on_checkbox_changed(path, state))

            # Check if image is selected
            if img_path in selection.selected_images:
                widget.checkbox.setChecked(True)

            # Set widget for item
            item.setSizeHint(widget.sizeHint())
            self.image_list.setItemWidget(item, widget)

        # Highlight active image
        if selection.active_image:
            for i in range(self.image_list.count()):
                item = self.image_list.item(i)
                img_path = item.data(Qt.UserRole)
                if img_path == selection.active_image:
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
                selection = self.app_manager.get_selection()
                selection.set_active(img_path)
                self.app_manager.update_selection()

    def _on_checkbox_changed(self, image_path: Path, state: int):
        """Handle checkbox state change"""
        if self._updating:
            return

        selection = self.app_manager.get_selection()
        if state == Qt.Checked:
            if image_path not in selection.selected_images:
                selection.selected_images.append(image_path)
        else:
            if image_path in selection.selected_images:
                selection.selected_images.remove(image_path)

        self.app_manager.update_selection()

    def _select_all(self):
        """Select all images in current list"""
        selection = self.app_manager.get_selection()
        images = selection.filtered_images if selection.filtered_images is not None else self.app_manager.get_project().get_all_absolute_image_paths()
        selection.select_all(images)
        self.app_manager.update_selection()

    def _remove_all(self):
        """Remove all selections"""
        selection = self.app_manager.get_selection()
        selection.clear_selection()
        self.app_manager.update_selection()

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

        selection = self.app_manager.get_selection()

        # Check if filtered images changed - if so, do full refresh
        current_filtered = tuple(selection.filtered_images) if selection.filtered_images is not None else None
        if current_filtered != self._last_filtered_images:
            self._last_filtered_images = current_filtered
            self.refresh()
            return

        # Check if selected images changed - if so, update checkboxes
        for i in range(self.image_list.count()):
            item = self.image_list.item(i)
            widget = self.image_list.itemWidget(item)
            if widget and hasattr(widget, 'checkbox'):
                img_path = item.data(Qt.UserRole)
                is_selected = img_path in selection.selected_images
                if widget.checkbox.isChecked() != is_selected:
                    self._updating = True
                    widget.checkbox.setChecked(is_selected)
                    self._updating = False

        # Update active image highlight
        if selection.active_image:
            for i in range(self.image_list.count()):
                item = self.image_list.item(i)
                img_path = item.data(Qt.UserRole)
                if img_path == selection.active_image:
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
        selection = self.app_manager.get_selection()

        # Determine which images to delete
        if selection.selected_images:
            images_to_delete = selection.selected_images.copy()
        elif selection.active_image:
            images_to_delete = [selection.active_image]
        else:
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
            self.app_manager.update_selection()
