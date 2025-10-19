"""
Import Images Dialog - Import single/multiple/directory with hashing
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
    QPushButton, QListWidget, QFileDialog, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt
from pathlib import Path
from datetime import datetime
import shutil

from .utils import hash_image
from .data_models import ImageData


class ImportDialog(QDialog):
    """Dialog for importing images into project with hashing and tagging"""

    def __init__(self, parent, app_manager):
        super().__init__(parent)
        self.app_manager = app_manager
        self.imported_count = 0
        self.imported_images = []

        self.setWindowTitle("Import Images")
        self.setMinimumSize(400, 300)
        self.resize(700, 500)  # Default size, but can be resized smaller

        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout(self)

        # Instructions
        label = QLabel("Select images to import into the project:")
        layout.addWidget(label)

        # List of selected files
        self.file_list = QListWidget()
        layout.addWidget(self.file_list)

        # Buttons
        button_layout = QHBoxLayout()

        single_btn = QPushButton("Add Single Image...")
        single_btn.clicked.connect(self._add_single)
        button_layout.addWidget(single_btn)

        multiple_btn = QPushButton("Add Multiple Images...")
        multiple_btn.clicked.connect(self._add_multiple)
        button_layout.addWidget(multiple_btn)

        directory_btn = QPushButton("Add Directory...")
        directory_btn.clicked.connect(self._add_directory)
        button_layout.addWidget(directory_btn)

        clear_btn = QPushButton("Clear List")
        clear_btn.clicked.connect(self.file_list.clear)
        button_layout.addWidget(clear_btn)

        layout.addLayout(button_layout)

        # Import options group
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout()

        # Add tag option
        tag_layout = QHBoxLayout()
        tag_layout.addWidget(QLabel("Add tag to images:"))
        self.tag_input = QLineEdit()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        default_category = self.app_manager.get_config().default_import_tag_category
        self.tag_input.setText(f"{default_category}:imported: {timestamp}")
        tag_layout.addWidget(self.tag_input)
        options_layout.addLayout(tag_layout)

        # Select after import checkbox
        self.select_after_import = QCheckBox("Select images after import")
        self.select_after_import.setChecked(True)
        options_layout.addWidget(self.select_after_import)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Dialog buttons
        dialog_btns = QHBoxLayout()
        dialog_btns.addStretch()

        import_btn = QPushButton("Import")
        import_btn.clicked.connect(self._import_images)
        import_btn.setDefault(True)
        dialog_btns.addWidget(import_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        dialog_btns.addWidget(cancel_btn)

        layout.addLayout(dialog_btns)

    def _add_single(self):
        """Add single image"""
        # ... (no change needed here, basic file dialog)
        project = self.app_manager.get_project()
        base_dir = project.get_base_directory()
        if not base_dir:
            return

        extensions = self.app_manager.get_config().default_image_extensions
        ext_filter = "Images (" + " ".join([f"*{ext}" for ext in extensions]) + ")"

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            str(base_dir),
            f"{ext_filter};;All Files (*)"
        )

        if file_path:
            self.file_list.addItem(file_path)

    def _add_multiple(self):
        """Add multiple images"""
        # ... (no change needed here, basic file dialog)
        project = self.app_manager.get_project()
        base_dir = project.get_base_directory()
        if not base_dir:
            return

        extensions = self.app_manager.get_config().default_image_extensions
        ext_filter = "Images (" + " ".join([f"*{ext}" for ext in extensions]) + ")"

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            str(base_dir),
            f"{ext_filter};;All Files (*)"
        )

        for file_path in file_paths:
            self.file_list.addItem(file_path)

    def _add_directory(self):
        """Add all images from directory recursively"""
        # ... (no change needed here, adds to list and shows count)
        project = self.app_manager.get_project()
        base_dir = project.get_base_directory()
        if not base_dir:
            return

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory",
            str(base_dir)
        )

        if not directory:
            return

        extensions = self.app_manager.get_config().default_image_extensions
        dir_path = Path(directory)

        # Find all images recursively
        count = 0
        for ext in extensions:
            for img_path in dir_path.rglob(f"*{ext}"):
                self.file_list.addItem(str(img_path))
                count += 1

        QMessageBox.information(self, "Found Images", f"Found {count} images in directory")

    def _import_images(self):
        """Import selected images into project with hashing and renaming"""
        project = self.app_manager.get_project()
        base_dir = project.get_base_directory()
        if not base_dir:
            QMessageBox.warning(self, "No Project", "No project loaded.")
            return

        # Ensure project has an image_list
        if not project.image_list:
            from .data_models import ImageList
            project.image_list = ImageList(base_dir)

        # Get all items from list
        image_paths = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            image_paths.append(Path(item.text()))

        if not image_paths:
            QMessageBox.warning(self, "No Images", "Please select images to import.")
            return

        # First pass: detect duplicates
        hash_length = self.app_manager.get_config().hash_length
        hash_map = {}  # hash -> list of source paths

        for img_path in image_paths:
            try:
                img_hash = hash_image(img_path, hash_length)
                if img_hash not in hash_map:
                    hash_map[img_hash] = []
                hash_map[img_hash].append(img_path)
            except Exception as e:
                print(f"Error hashing {img_path}: {e}")

        # Find duplicates
        duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}

        if duplicates:
            # Build duplicate summary message
            dup_count = sum(len(paths) - 1 for paths in duplicates.values())
            summary_lines = []
            for img_hash, paths in list(duplicates.items())[:5]:  # Show first 5
                summary_lines.append(f"  {img_hash}: {len(paths)} copies")
            if len(duplicates) > 5:
                summary_lines.append(f"  ... and {len(duplicates) - 5} more")

            duplicate_summary = "\n".join(summary_lines)

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("Duplicate Images Found")
            msg_box.setText(f"Found {dup_count} duplicate images.")
            msg_box.setInformativeText(
                f"These images have identical content:\n\n{duplicate_summary}\n\n"
                "Keep only one copy of each, or cancel import?"
            )

            # Add buttons
            delete_btn = msg_box.addButton("Keep One Copy", QMessageBox.AcceptRole)
            keep_all_btn = msg_box.addButton("Keep All", QMessageBox.AcceptRole)
            cancel_btn = msg_box.addButton("Cancel Import", QMessageBox.RejectRole)
            msg_box.setDefaultButton(delete_btn)

            msg_box.exec_()
            clicked = msg_box.clickedButton()

            if clicked == cancel_btn:
                return
            elif clicked == delete_btn:
                # Keep only first copy of each duplicate, remove rest from image_paths
                # Build set of paths to keep (first of each duplicate group)
                paths_to_remove = set()
                for img_hash, paths in duplicates.items():
                    # Remove all but the first
                    for path in paths[1:]:
                        paths_to_remove.add(path)

                # Filter image_paths to remove duplicates
                image_paths = [p for p in image_paths if p not in paths_to_remove]
            # If keep_all_btn clicked, do nothing and continue with all images

        # Parse tag input (category:value)
        tag_text = self.tag_input.text().strip()
        tag_category = None
        tag_value = None
        if tag_text:
            parts = tag_text.split(':', 1)
            if len(parts) == 2:
                tag_category = parts[0].strip()
                tag_value = parts[1].strip()

        # Import images
        added = 0
        self.imported_images = []

        for img_path in image_paths:
            try:
                # Generate hash for the image
                img_hash = hash_image(img_path, hash_length)
                ext = img_path.suffix

                # New filename is hash + extension
                new_filename = f"{img_hash}{ext}"
                new_path = base_dir / new_filename

                # Move/rename image to project directory
                if img_path == new_path:
                    # Already in place with correct name
                    pass
                elif img_path.parent == base_dir:
                    # In project dir but wrong name - rename it
                    shutil.move(str(img_path), str(new_path))
                else:
                    # Outside project dir - move it in
                    if new_path.exists():
                        # Target exists, skip moving (but still try to add to project)
                        pass
                    else:
                        shutil.move(str(img_path), str(new_path))

                # Try to add to project (will only add if not already in project)
                if project.image_list.add_image(new_path):
                    added += 1
                    self.imported_images.append(new_path)

                # Create/update JSON file (do this even if already in project)
                json_path = project.get_image_json_path(new_path)

                # Check if JSON file exists
                if json_path.exists():
                    img_data = ImageData.load(json_path)
                else:
                    img_data = ImageData(name=img_hash)

                # Add import tag if specified
                if tag_category and tag_value:
                    img_data.add_tag(tag_category, tag_value)

                # Save JSON
                img_data.save(json_path)

            except Exception as e:
                print(f"Error importing {img_path}: {e}")

        self.imported_count = added

        # Update selection if requested
        if self.select_after_import and self.imported_images:
            # Clear current selection and select imported images
            if project.image_list:
                project.image_list.clear_selection()
                for img_path in self.imported_images:
                    project.image_list.select(img_path)
                # Set first imported image as active
                if self.imported_images:
                    project.image_list.set_active(self.imported_images[0])

        if added == 0:
            QMessageBox.information(self, "Import Complete", "No new images were imported.")
        else:
            QMessageBox.information(self, "Import Complete", f"Imported {added} new images.")

        self.accept()