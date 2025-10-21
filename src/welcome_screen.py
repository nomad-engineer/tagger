"""
Welcome Screen - Library selection dialog shown at startup
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QInputDialog, QMessageBox, QWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from pathlib import Path
from typing import Optional


class WelcomeScreen(QDialog):
    """Welcome screen for creating/opening libraries"""

    def __init__(self, app_manager, parent=None):
        super().__init__(parent)
        self.app_manager = app_manager
        self.selected_library_file: Optional[Path] = None

        self.setWindowTitle("Welcome to Image Tagger")
        self.setMinimumSize(600, 400)
        self.setModal(True)

        self._setup_ui()
        self._load_recent_libraries()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Welcome to Image Tagger")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Select or create a library to get started")
        subtitle.setStyleSheet("color: gray; font-size: 12px;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        # Action buttons
        buttons_layout = QHBoxLayout()

        new_library_btn = QPushButton("Create New Library")
        new_library_btn.clicked.connect(self._create_new_library)
        new_library_btn.setMinimumHeight(40)
        buttons_layout.addWidget(new_library_btn)

        open_library_btn = QPushButton("Open Existing Library")
        open_library_btn.clicked.connect(self._open_existing_library)
        open_library_btn.setMinimumHeight(40)
        buttons_layout.addWidget(open_library_btn)

        layout.addLayout(buttons_layout)

        layout.addSpacing(20)

        # Recent libraries section
        recent_label = QLabel("Recent Libraries:")
        recent_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(recent_label)

        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(self._open_recent_library)
        layout.addWidget(self.recent_list)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        quit_btn = QPushButton("Quit")
        quit_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(quit_btn)

        layout.addLayout(bottom_layout)

    def _load_recent_libraries(self):
        """Load recent libraries from config"""
        self.recent_list.clear()

        for library_path_str in self.app_manager.get_config().recent_libraries:
            library_path = Path(library_path_str)

            # Create list item with delete button
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(2, 2, 2, 2)

            # Library name and path
            if library_path.exists():
                label_text = f"{library_path.parent.name} - {library_path.parent}"
                label = QLabel(label_text)
            else:
                label_text = f"{library_path.parent.name} - {library_path.parent} (not found)"
                label = QLabel(label_text)
                label.setStyleSheet("color: gray; font-style: italic;")

            item_layout.addWidget(label)

            # Remove button
            remove_btn = QPushButton("×")
            remove_btn.setMaximumWidth(30)
            remove_btn.setToolTip("Remove from recent libraries")
            remove_btn.clicked.connect(lambda checked, path=library_path_str: self._remove_recent_library(path))
            item_layout.addWidget(remove_btn)

            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, library_path_str)
            self.recent_list.addItem(list_item)
            self.recent_list.setItemWidget(list_item, item_widget)

        if self.recent_list.count() == 0:
            placeholder = QListWidgetItem("No recent libraries")
            placeholder.setFlags(Qt.NoItemFlags)
            self.recent_list.addItem(placeholder)

    def _create_new_library(self):
        """Create a new library"""
        # Ask for library name
        library_name, ok = QInputDialog.getText(
            self,
            "Create New Library",
            "Enter library name:"
        )

        if not ok or not library_name.strip():
            return

        library_name = library_name.strip()

        # Ask for library location
        library_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Directory for New Library",
            str(Path.home())
        )

        if not library_dir:
            return

        library_path = Path(library_dir)

        # Check if library.json already exists
        library_file = library_path / "library.json"
        if library_file.exists():
            QMessageBox.warning(
                self,
                "Library Exists",
                f"A library already exists at {library_path}.\n\nPlease choose a different directory."
            )
            return

        # Create the library
        try:
            self.app_manager.create_library(library_path, library_name)
            self.selected_library_file = library_file
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create library:\n\n{str(e)}"
            )

    def _open_existing_library(self):
        """Open an existing library"""
        library_file, _ = QFileDialog.getOpenFileName(
            self,
            "Open Library",
            str(Path.home()),
            "Library Files (library.json);;All Files (*)"
        )

        if not library_file:
            return

        library_path = Path(library_file)

        if not library_path.exists():
            QMessageBox.warning(
                self,
                "Not Found",
                f"Library file not found:\n\n{library_path}"
            )
            return

        # Load the library
        try:
            self.app_manager.load_library(library_path)
            self.selected_library_file = library_path
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open library:\n\n{str(e)}"
            )

    def _open_recent_library(self, item):
        """Open a library from recent list"""
        library_path_str = item.data(Qt.UserRole)
        if not library_path_str:
            return

        library_path = Path(library_path_str)

        if not library_path.exists():
            QMessageBox.warning(
                self,
                "Not Found",
                f"Library file not found:\n\n{library_path}\n\nIt may have been moved or deleted."
            )
            return

        # Load the library
        try:
            self.app_manager.load_library(library_path)
            self.selected_library_file = library_path
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open library:\n\n{str(e)}"
            )

    def _remove_recent_library(self, library_path_str: str):
        """Remove a library from recent list"""
        config = self.app_manager.get_config()
        if library_path_str in config.recent_libraries:
            config.recent_libraries.remove(library_path_str)
            self.app_manager.config_manager.save_config(config)
            self._load_recent_libraries()

    def get_selected_library(self) -> Optional[Path]:
        """Get the selected library file"""
        return self.selected_library_file
