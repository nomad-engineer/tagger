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

        # Initialize plugin system
        from .plugin_manager import PluginManager
        self.plugin_manager = PluginManager()
        self.plugin_windows = {}  # Store plugin window instances

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

        # Windows Menu (all shortcuts work application-wide)
        windows_menu = menubar.addMenu("&Windows")

        gallery_action = QAction("&Gallery", self)
        gallery_action.setShortcut("Ctrl+G")
        gallery_action.setShortcutContext(Qt.ApplicationShortcut)
        gallery_action.triggered.connect(self.show_gallery)
        windows_menu.addAction(gallery_action)

        filter_action = QAction("&Filter", self)
        filter_action.setShortcut("Ctrl+F")
        filter_action.setShortcutContext(Qt.ApplicationShortcut)
        filter_action.triggered.connect(self.show_filter)
        windows_menu.addAction(filter_action)

        tag_action = QAction("&Tag", self)
        tag_action.setShortcut("Ctrl+T")
        tag_action.setShortcutContext(Qt.ApplicationShortcut)
        tag_action.triggered.connect(self.show_tag)
        windows_menu.addAction(tag_action)

        windows_menu.addSeparator()

        # Global navigation shortcuts (work from any window)
        prev_image_action = QAction("Previous Image", self)
        prev_image_action.setShortcut("Ctrl+Up")
        prev_image_action.setShortcutContext(Qt.ApplicationShortcut)  # Works globally
        prev_image_action.triggered.connect(lambda: self._navigate_image(-1))
        windows_menu.addAction(prev_image_action)

        next_image_action = QAction("Next Image", self)
        next_image_action.setShortcut("Ctrl+Down")
        next_image_action.setShortcutContext(Qt.ApplicationShortcut)  # Works globally
        next_image_action.triggered.connect(lambda: self._navigate_image(1))
        windows_menu.addAction(next_image_action)

        # Tools Menu (dynamically populated from plugins)
        tools_menu = menubar.addMenu("&Tools")
        self._populate_tools_menu(tools_menu)

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
        # Select where to save the .json file using persistent dialog
        project_file = self.app_manager.get_save_filename(
            self,
            "Create New Project",
            "untitled_project.json",
            "Project Files (*.json);;All Files (*)"
        )

        if not project_file:
            return

        # Get project name
        project_name, ok = QInputDialog.getText(
            self,
            "Project Name",
            "Enter project name:",
            text=project_file.stem
        )

        if not ok or not project_name:
            return

        # Create project with ProjectData
        from .data_models import ProjectData, ImageList
        project = ProjectData(
            project_name=project_name,
            project_file=project_file,
            image_list=ImageList(project_file.parent)
        )

        project.save()

        # Load project
        self.app_manager.load_project(project_file)

        self.statusBar().showMessage(f"Created project: {project_name}", 3000)

    def open_project(self):
        """Open existing project"""
        # Use persistent file dialog
        project_file = self.app_manager.get_open_filename(
            self,
            "Open Project",
            "Project Files (*.json);;All Files (*)"
        )

        if project_file:
            self.app_manager.load_project(project_file)
            self.statusBar().showMessage(f"Opened: {self.app_manager.get_project().project_name}", 3000)

    def save_project(self):
        """Save current project with confirmation"""
        project = self.app_manager.get_project()
        if not project.project_file:
            self.statusBar().showMessage("No project loaded", 2000)
            return

        # Check if there are pending changes
        pending = self.app_manager.get_pending_changes()
        if not pending.has_changes():
            self.statusBar().showMessage("No changes to save", 2000)
            return

        # Show confirmation dialog with change summary
        summary = pending.get_summary()
        change_count = pending.get_change_count()

        reply = QMessageBox.question(
            self,
            "Confirm Save",
            f"Save {change_count} change(s) to disk?\n\n{summary}",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save
        )

        if reply == QMessageBox.StandardButton.Save:
            if self.app_manager.commit_all_changes():
                self.statusBar().showMessage("Project saved", 2000)
            else:
                self.statusBar().showMessage("Save failed", 2000)
        else:
            self.statusBar().showMessage("Save cancelled", 2000)

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

    def show_filter(self):
        """Show filter window"""
        from .filter_window import Filter
        if not hasattr(self, 'filter_window') or not self.filter_window:
            self.filter_window = Filter(self.app_manager)
        self.filter_window.show()
        self.filter_window.raise_()
        self.filter_window.activateWindow()

    def show_tag(self):
        """Show tag editor window"""
        from .tag_window import TagWindow
        if not hasattr(self, 'tag_window') or not self.tag_window:
            self.tag_window = TagWindow(self.app_manager)
        self.tag_window.show()
        self.tag_window.raise_()
        self.tag_window.activateWindow()

    def _populate_tools_menu(self, menu):
        """Populate Tools menu with discovered plugins"""
        plugins = self.plugin_manager.get_plugins()

        if not plugins:
            no_plugins_action = QAction("(No plugins available)", self)
            no_plugins_action.setEnabled(False)
            menu.addAction(no_plugins_action)
            return

        for plugin_name, plugin_class in plugins.items():
            # Instantiate plugin to get metadata
            try:
                # For PluginWindow subclasses, we need to pass app_manager
                temp_instance = plugin_class(self.app_manager)

                action = QAction(temp_instance.get_name(), self)

                # Set shortcut if available
                shortcut = temp_instance.get_shortcut()
                if shortcut:
                    action.setShortcut(shortcut)
                    action.setShortcutContext(Qt.ApplicationShortcut)

                # Connect to show_plugin with plugin name
                action.triggered.connect(lambda checked, name=plugin_name: self.show_plugin(name))
                menu.addAction(action)

            except Exception as e:
                print(f"Error adding plugin {plugin_name} to menu: {e}")

    def show_plugin(self, plugin_name: str):
        """Show a plugin window"""
        # Check if window already exists
        if plugin_name in self.plugin_windows and self.plugin_windows[plugin_name]:
            window = self.plugin_windows[plugin_name]
            window.show()
            window.raise_()
            window.activateWindow()
            return

        # Create new plugin window
        plugin_class = self.plugin_manager.get_plugin(plugin_name)
        if plugin_class:
            try:
                window = plugin_class(self.app_manager)
                self.plugin_windows[plugin_name] = window
                window.show()
                window.raise_()
                window.activateWindow()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Plugin Error",
                    f"Error loading plugin '{plugin_name}':\n{e}"
                )
                import traceback
                traceback.print_exc()

    def _navigate_image(self, direction: int):
        """Navigate to next or previous image (global shortcut)

        Args:
            direction: 1 for next, -1 for previous
        """
        current_view = self.app_manager.get_current_view()
        if not current_view:
            return

        # Get all images from current view
        all_images = current_view.get_all_paths()
        active_image = current_view.get_active()

        if not all_images or not active_image:
            return

        try:
            current_idx = all_images.index(active_image)
            new_idx = current_idx + direction

            # Wrap around
            if new_idx < 0:
                new_idx = len(all_images) - 1
            elif new_idx >= len(all_images):
                new_idx = 0

            current_view.set_active(all_images[new_idx])
            self.app_manager.update_project(save=False)
        except ValueError:
            # Active image not in list, just select first
            if all_images:
                current_view.set_active(all_images[0])
                self.app_manager.update_project(save=False)

    def closeEvent(self, event):
        """Handle close event - check for unsaved changes, close all child windows"""
        # Check for unsaved changes
        pending = self.app_manager.get_pending_changes()
        if pending.has_changes():
            summary = pending.get_summary()
            change_count = pending.get_change_count()

            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"You have {change_count} unsaved change(s).\n\n{summary}\n\nDo you want to save before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )

            if reply == QMessageBox.StandardButton.Save:
                if not self.app_manager.commit_all_changes():
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            # If Discard, continue with close

        # Close all child windows
        if hasattr(self, 'gallery_window') and self.gallery_window:
            self.gallery_window.close()
        if hasattr(self, 'filter_window') and self.filter_window:
            self.filter_window.close()
        if hasattr(self, 'tag_window') and self.tag_window:
            self.tag_window.close()
        if hasattr(self, 'export_window') and self.export_window:
            self.export_window.close()

        # Close all plugin windows
        for plugin_name, window in self.plugin_windows.items():
            if window:
                window.close()

        event.accept()
