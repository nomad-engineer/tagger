"""
Manage Image Library Plugin - Tools to manage image files on disk
"""
import os
from typing import List, Set
from pathlib import Path
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QDialog, QDialogButtonBox, QWidget, QCheckBox
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QPixmapCache, QIcon

from ..plugin_base import PluginWindow


class UnusedImageItemWidget(QWidget):
    """Custom widget for unused image list items with thumbnail"""

    def __init__(self, image_path: Path, thumbnail_size: int = 100, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.thumbnail_size = thumbnail_size
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(self.thumbnail_size, self.thumbnail_size)
        self.thumbnail_label.setScaledContents(False)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)

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

        layout.addWidget(self.thumbnail_label)

        # File path and size info
        info_layout = QVBoxLayout()

        # File path
        path_label = QLabel(str(self.image_path))
        path_label.setWordWrap(True)
        info_layout.addWidget(path_label)

        # File size
        try:
            file_size = self.image_path.stat().st_size
            size_str = self._format_file_size(file_size)
            size_label = QLabel(f"Size: {size_str}")
            size_label.setStyleSheet("color: gray; font-size: 10px;")
            info_layout.addWidget(size_label)
        except Exception:
            pass

        info_layout.addStretch()
        layout.addLayout(info_layout, 1)

    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"


class UnusedImagesDialog(QDialog):
    """Dialog to show unused images and confirm deletion"""

    def __init__(self, unused_images: List[Path], parent=None):
        super().__init__(parent)
        self.unused_images = unused_images
        self.setWindowTitle("Unused Images")
        self.resize(700, 500)
        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout(self)

        # Message
        count = len(self.unused_images)
        message = QLabel(f"Permanently delete {count} image{'s' if count != 1 else ''} from library?")
        message.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(message)

        # Warning
        warning = QLabel("⚠️ This will permanently delete the files from disk. This cannot be undone.")
        warning.setStyleSheet("color: #d32f2f; font-size: 11px;")
        layout.addWidget(warning)

        # List of files
        files_label = QLabel("Files to be deleted:")
        layout.addWidget(files_label)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.NoSelection)

        # Populate list with thumbnails
        for img_path in self.unused_images:
            # Create list item
            item = QListWidgetItem()
            self.file_list.addItem(item)

            # Create custom widget with thumbnail
            widget = UnusedImageItemWidget(img_path, thumbnail_size=100)

            # Set widget for item
            item.setSizeHint(widget.sizeHint())
            self.file_list.setItemWidget(item, widget)

        layout.addWidget(self.file_list)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


class ManageLibraryPlugin(PluginWindow):
    """Plugin to manage image library on disk"""

    def __init__(self, app_manager, parent=None):
        super().__init__(app_manager, parent)

        self.name = "Manage Image Library"
        self.description = "Tools to manage image files on disk"
        self.shortcut = None

        self.setWindowTitle(self.name)
        self.resize(500, 300)

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self.scroll_content)

        # Title and description
        title = QLabel("Manage Image Library")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        description = QLabel("Tools to manage image files on disk")
        description.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(description)

        layout.addSpacing(20)

        # Remove unused images section
        unused_group_label = QLabel("Remove Unused Images")
        unused_group_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(unused_group_label)

        unused_description = QLabel(
            "Scan for images in the project directory that are not used in the project.\n"
            "Unused images can be permanently deleted from disk."
        )
        unused_description.setWordWrap(True)
        unused_description.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(unused_description)

        # Button
        self.remove_unused_btn = QPushButton("Remove Unused Images from Library")
        self.remove_unused_btn.clicked.connect(self._remove_unused_images)
        layout.addWidget(self.remove_unused_btn)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

    def _remove_unused_images(self):
        """Scan for and remove unused images"""
        project = self.app_manager.get_project()

        if not project.project_file:
            QMessageBox.warning(
                self,
                "No Project",
                "Please open or create a project first."
            )
            return

        # Get project root directory
        project_root = project.get_base_directory()
        if not project_root or not project_root.exists():
            QMessageBox.warning(
                self,
                "Invalid Project",
                "Project root directory does not exist."
            )
            return

        self.status_label.setText("Scanning for unused images...")
        self.remove_unused_btn.setEnabled(False)

        try:
            # Find unused images
            unused_images = self._find_unused_images(project_root)

            self.status_label.setText("")
            self.remove_unused_btn.setEnabled(True)

            if not unused_images:
                QMessageBox.information(
                    self,
                    "No Unused Images",
                    "No unused images found in the library."
                )
                return

            # Show dialog with unused images
            dialog = UnusedImagesDialog(unused_images, self)
            result = dialog.exec_()

            if result == QDialog.Accepted:
                # Delete the files
                deleted_count = 0
                failed_count = 0

                for img_path in unused_images:
                    try:
                        img_path.unlink()
                        deleted_count += 1
                    except Exception as e:
                        failed_count += 1
                        print(f"Failed to delete {img_path}: {e}")

                # Show result
                if failed_count == 0:
                    QMessageBox.information(
                        self,
                        "Success",
                        f"Successfully deleted {deleted_count} unused image{'s' if deleted_count != 1 else ''}."
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Partial Success",
                        f"Deleted {deleted_count} image{'s' if deleted_count != 1 else ''}.\n"
                        f"Failed to delete {failed_count} image{'s' if failed_count != 1 else ''}."
                    )

        except Exception as e:
            self.status_label.setText("")
            self.remove_unused_btn.setEnabled(True)
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while scanning for unused images:\n{str(e)}"
            )

    def _find_unused_images(self, project_root: Path) -> List[Path]:
        """
        Find all images in project root that are not used in the project

        Args:
            project_root: Root directory to scan

        Returns:
            List of unused image paths
        """
        # Get all images in project
        used_images = set()
        image_list = self.app_manager.get_image_list()
        if image_list is not None:
            used_images = set(image_list.get_all_paths())

        # Get all image files in project directory
        config = self.app_manager.get_config()
        extensions = config.default_image_extensions

        all_images = set()
        for ext in extensions:
            # Use rglob to search recursively
            for img_path in project_root.rglob(f"*{ext}"):
                if img_path.is_file():
                    all_images.add(img_path)

        # Find unused images (in directory but not in project)
        unused_images = all_images - used_images

        return sorted(list(unused_images))
