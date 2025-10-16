"""
Main Window - Simple container with menu and swappable view
"""
from PyQt5.QtWidgets import (
    QMainWindow, QAction, QWidget, QVBoxLayout,
    QFileDialog, QInputDialog, QMessageBox
)
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt
from pathlib import Path


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self, app_manager):
        super().__init__()
        self.app_manager = app_manager

        self.setWindowTitle("Image Tagger")
        self.setGeometry(100, 100, 1200, 800)

        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()

        # Connect to config changes for recent menu updates
        self.app_manager.config_changed.connect(self._update_recent_menu)

    def _setup_ui(self):
        """Setup main UI - container for swappable views"""
        # Central widget container
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Load image viewer as default view
        from .image_viewer import ImageViewer
        self.current_view = ImageViewer(self.app_manager, self.central_widget)
        self.main_layout.addWidget(self.current_view)

    def _setup_menu(self):
        """Setup menu bar"""
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        new_action = QAction("&New Project", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_project)
        file_menu.addAction(new_action)

        open_action = QAction("&Open Project", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_project)
        file_menu.addAction(open_action)

        save_action = QAction("&Save Project", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        import_action = QAction("&Import Images...", self)
        import_action.setShortcut("Ctrl+I")
        import_action.triggered.connect(self.import_images)
        file_menu.addAction(import_action)

        file_menu.addSeparator()

        # Recent projects submenu
        self.recent_menu = file_menu.addMenu("Recent Projects")
        self._update_recent_menu()

        file_menu.addSeparator()

        quit_action = QAction("E&xit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit Menu
        edit_menu = menubar.addMenu("&Edit")

        prefs_action = QAction("&Preferences", self)
        prefs_action.setShortcut("Ctrl+,")
        prefs_action.triggered.connect(self.show_preferences)
        edit_menu.addAction(prefs_action)

        # Tools Menu
        tools_menu = menubar.addMenu("&Tools")

        gallery_action = QAction("&Gallery", self)
        gallery_action.setShortcut("Ctrl+G")
        gallery_action.triggered.connect(self.show_gallery)
        tools_menu.addAction(gallery_action)

        # Help Menu
        help_menu = menubar.addMenu("&Help")

        docs_action = QAction("&Documentation", self)
        docs_action.setShortcut(QKeySequence.StandardKey.HelpContents)
        docs_action.triggered.connect(self.show_documentation)
        help_menu.addAction(docs_action)

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _setup_statusbar(self):
        """Setup status bar"""
        self.statusBar().showMessage("Ready")

    def _update_recent_menu(self):
        """Update recent projects menu"""
        self.recent_menu.clear()
        recent = self.app_manager.get_config().recent_projects

        if not recent:
            action = QAction("(No recent projects)", self)
            action.setEnabled(False)
            self.recent_menu.addAction(action)
        else:
            for path in recent[:10]:
                action = QAction(path, self)
                action.triggered.connect(lambda checked, p=path: self._open_recent(p))
                self.recent_menu.addAction(action)

    def _open_recent(self, path: str):
        """Open a recent project"""
        self.app_manager.load_project(Path(path))
        self.statusBar().showMessage(f"Opened: {self.app_manager.get_project().project_name}", 3000)

    # Menu actions
    def new_project(self):
        """Create new project"""
        # Select where to save the .json file
        project_file, _ = QFileDialog.getSaveFileName(
            self,
            "Create New Project",
            str(Path.home() / "untitled_project.json"),
            "Project Files (*.json);;All Files (*)"
        )

        if not project_file:
            return

        project_file = Path(project_file)

        # Get project name
        project_name, ok = QInputDialog.getText(
            self,
            "Project Name",
            "Enter project name:",
            text=project_file.stem
        )

        if not ok or not project_name:
            return

        # Create project
        project = self.app_manager.get_project()
        project.project_name = project_name
        project.project_file = project_file
        project.images = []  # No automatic scanning

        project.save()

        # Load project
        self.app_manager.load_project(project_file)

        self.statusBar().showMessage(f"Created project: {project_name}", 3000)

    def open_project(self):
        """Open existing project"""
        project_file, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(Path.home()),
            "Project Files (*.json);;All Files (*)"
        )

        if project_file:
            self.app_manager.load_project(Path(project_file))
            self.statusBar().showMessage(f"Opened: {self.app_manager.get_project().project_name}", 3000)

    def save_project(self):
        """Save current project"""
        project = self.app_manager.get_project()
        if project.project_file:
            self.app_manager.save_project()
            self.statusBar().showMessage("Project saved", 2000)
        else:
            self.statusBar().showMessage("No project loaded", 2000)

    def import_images(self):
        """Import images into project"""
        project = self.app_manager.get_project()
        if not project.project_file:
            QMessageBox.warning(self, "No Project", "Please create or open a project first.")
            return

        # Show import dialog
        from .import_dialog import ImportDialog
        dialog = ImportDialog(self, self.app_manager)
        if dialog.exec():
            count = dialog.imported_count
            self.app_manager.update_project(save=True)
            self.statusBar().showMessage(f"Imported {count} images", 3000)

    def show_preferences(self):
        """Show preferences dialog"""
        QMessageBox.information(
            self,
            "Preferences",
            f"Preferences not yet implemented.\n\nConfig location:\n{self.app_manager.config_manager.get_config_path()}"
        )

    def show_documentation(self):
        """Show documentation"""
        QMessageBox.information(
            self,
            "Documentation",
            "Documentation:\n\n"
            "• File → New Project: Create project\n"
            "• File → Open Project: Open project\n"
            "• Use arrow buttons to navigate images\n\n"
            "See README.md for details"
        )

    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About Image Tagger",
            "Image Tagger v0.2.0\n\nSimple PyQt5 application template"
        )

    def show_gallery(self):
        """Show gallery window"""
        from .gallery import Gallery
        if not hasattr(self, 'gallery_window') or not self.gallery_window:
            self.gallery_window = Gallery(self.app_manager)
        self.gallery_window.show()
        self.gallery_window.raise_()
        self.gallery_window.activateWindow()

    def closeEvent(self, event):
        """Handle close event"""
        if self.app_manager.get_project().project_file:
            self.app_manager.save_project()
        event.accept()
