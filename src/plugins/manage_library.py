"""
Manage Image Library Plugin - Tools to manage image files on disk
"""
import os
import shutil
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

        layout.addSpacing(20)

        # Move images section
        move_group_label = QLabel("Move Selected Images")
        move_group_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(move_group_label)

        move_description = QLabel(
            "Move selected images (or active image) to a different directory.\n"
            "Image files and their data files will be moved, and paths will be updated in the project."
        )
        move_description.setWordWrap(True)
        move_description.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(move_description)

        # Button
        self.move_images_btn = QPushButton("Move Selected Images to Directory...")
        self.move_images_btn.clicked.connect(self._move_selected_images)
        layout.addWidget(self.move_images_btn)

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

    def _move_selected_images(self):
        """Move selected images to another directory"""
        project = self.app_manager.get_project()

        if not project.project_file:
            QMessageBox.warning(
                self,
                "No Project",
                "Please open or create a project first."
            )
            return

        # Get images to move (selected or active)
        current_view = self.app_manager.get_current_view()
        if current_view is None:
            QMessageBox.warning(
                self,
                "No Images",
                "No images in project."
            )
            return

        images_to_move = current_view.get_working_images()
        if not images_to_move:
            QMessageBox.information(
                self,
                "No Selection",
                "No images selected. Please select images in the gallery first."
            )
            return

        # Get project root directory as default starting point
        project_root = project.get_base_directory()
        if not project_root or not project_root.exists():
            QMessageBox.warning(
                self,
                "Invalid Project",
                "Project root directory does not exist."
            )
            return

        # Show confirmation
        count = len(images_to_move)
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("Move Images")
        msg_box.setText(f"Move {count} image{'s' if count != 1 else ''} to a new directory?")
        msg_box.setInformativeText("This will move both the image files and their data files (.json).")
        msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg_box.setDefaultButton(QMessageBox.Ok)

        result = msg_box.exec_()
        if result != QMessageBox.Ok:
            return

        # Select destination directory
        dest_dir = self.app_manager.get_existing_directory(
            self,
            "Select Destination Directory",
            'project',
            default_dir=project_root
        )

        if not dest_dir:
            return

        # Ensure destination is a directory
        if not dest_dir.is_dir():
            QMessageBox.warning(
                self,
                "Invalid Directory",
                "Selected path is not a directory."
            )
            return

        # Track moved images and their new paths
        moved_images = []  # [(old_path, new_path), ...]
        failed_count = 0

        for old_img_path in images_to_move:
            try:
                # Generate new paths
                new_img_path = dest_dir / old_img_path.name

                # Check if file already exists at destination
                if new_img_path.exists() and new_img_path != old_img_path:
                    reply = QMessageBox.question(
                        self,
                        "File Exists",
                        f"File {new_img_path.name} already exists in destination.\n\nOverwrite?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if reply != QMessageBox.Yes:
                        failed_count += 1
                        continue

                # Get JSON data file path
                old_json_path = project.get_image_json_path(old_img_path)
                new_json_path = dest_dir / old_json_path.name

                # Move image file
                if old_img_path != new_img_path:
                    shutil.move(str(old_img_path), str(new_img_path))

                # Move JSON data file if it exists
                if old_json_path.exists() and old_json_path != new_json_path:
                    shutil.move(str(old_json_path), str(new_json_path))

                moved_images.append((old_img_path, new_img_path))

            except Exception as e:
                print(f"Failed to move {old_img_path}: {e}")
                failed_count += 1

        if not moved_images:
            QMessageBox.warning(
                self,
                "No Images Moved",
                "No images were moved."
            )
            return

        # Update ImageList with new paths
        image_list = self.app_manager.get_image_list()
        if image_list is not None:
            for old_path, new_path in moved_images:
                # Update path in image list
                image_list.update_image_path(old_path, new_path)

        # Mark project as modified
        self.app_manager.update_project(save=True)

        # Show result
        success_count = len(moved_images)
        if failed_count == 0:
            QMessageBox.information(
                self,
                "Success",
                f"Successfully moved {success_count} image{'s' if success_count != 1 else ''} to:\n{dest_dir}"
            )
        else:
            QMessageBox.warning(
                self,
                "Partial Success",
                f"Moved {success_count} image{'s' if success_count != 1 else ''}.\n"
                f"Failed to move {failed_count} image{'s' if failed_count != 1 else ''}."
            )
