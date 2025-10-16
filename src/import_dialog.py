"""
Import Images Dialog - Import single/multiple/directory
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt
from pathlib import Path


class ImportDialog(QDialog):
    """Dialog for importing images into project"""

    def __init__(self, parent, app_manager):
        super().__init__(parent)
        self.app_manager = app_manager
        self.imported_count = 0

        self.setWindowTitle("Import Images")
        self.setMinimumSize(600, 400)

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
        """Import selected images into project"""
        project = self.app_manager.get_project()

        # Get all items from list
        image_paths = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            image_paths.append(Path(item.text()))

        if not image_paths:
            QMessageBox.warning(self, "No Images", "Please select images to import.")
            return

        # Add to project
        added = 0
        for img_path in image_paths:
            if project.add_image(img_path):
                added += 1

        self.imported_count = added

        if added == 0:
            QMessageBox.information(self, "Import Complete", "All selected images were already in the project.")
        else:
            QMessageBox.information(self, "Import Complete", f"Imported {added} new images.")

        self.accept()
