"""
Main Window - Simple container with menu and swappable view
"""

from PyQt5.QtWidgets import (
    QMainWindow,
    QAction,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QComboBox,
    QLabel,
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

        # Connect to app manager signals for updating UI state
        self.app_manager.library_changed.connect(self._update_window_title)
        self.app_manager.project_changed.connect(self._update_window_title)
        self.app_manager.project_changed.connect(self._update_status_bar)

    def _setup_ui(self):
        """Setup main UI - container for swappable views"""
        # Central widget container
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Add view selector toolbar
        self._setup_view_selector()

        # Load image viewer as default view
        from .image_viewer import ImageViewer

        self.current_view = ImageViewer(self.app_manager, self.central_widget)
        self.main_layout.addWidget(self.current_view)

    def _setup_menu(self):
        """Setup menu bar"""
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        open_action = QAction("&Open", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.show_welcome_screen)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        manage_projects_action = QAction("Manage &Projects...", self)
        manage_projects_action.setShortcut("Ctrl+P")
        manage_projects_action.triggered.connect(self.show_manage_projects)
        file_menu.addAction(manage_projects_action)

        file_menu.addSeparator()

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.setShortcutContext(Qt.ApplicationShortcut)  # Works from any window
        save_action.triggered.connect(self.save_all)
        file_menu.addAction(save_action)

        revert_action = QAction("Re&vert to Saved", self)
        revert_action.setShortcut("Ctrl+Shift+R")
        revert_action.setShortcutContext(
            Qt.ApplicationShortcut
        )  # Works from any window
        revert_action.triggered.connect(self.revert_all)
        file_menu.addAction(revert_action)

        refresh_from_disk_action = QAction("Refresh from &Disk", self)
        refresh_from_disk_action.setShortcut("Ctrl+R")
        refresh_from_disk_action.setShortcutContext(
            Qt.ApplicationShortcut
        )  # Works from any window
        refresh_from_disk_action.triggered.connect(self.refresh_from_disk)
        file_menu.addAction(refresh_from_disk_action)

        file_menu.addSeparator()

        import_action = QAction("&Import Images...", self)
        import_action.setShortcut("Ctrl+I")
        import_action.triggered.connect(self.import_images)
        file_menu.addAction(import_action)

        file_menu.addSeparator()

        refresh_action = QAction("&Refresh UI", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_fuzzy_finder)
        file_menu.addAction(refresh_action)

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

    def _update_window_title(self):
        """Update window title to show library name and unsaved changes indicator"""
        library = self.app_manager.get_library()
        project = self.app_manager.get_project()
        pending = self.app_manager.get_pending_changes()

        # Build title
        title_parts = []

        # Add view name
        if (
            self.app_manager.current_view_mode == "project"
            and project
            and project.project_name
        ):
            title_parts.append(project.project_name)
        elif library and library.library_name:
            title_parts.append(library.library_name)

        # Add unsaved changes indicator
        if pending.has_changes():
            if title_parts:
                title_parts[0] = f"*{title_parts[0]}"
            else:
                title_parts.append("*Untitled")

        # Add app name
        title_parts.append("Image Tagger")

        self.setWindowTitle(" - ".join(title_parts))

    def _update_status_bar(self):
        """Update status bar to show unsaved changes count"""
        pending = self.app_manager.get_pending_changes()

        if pending.has_changes():
            change_count = pending.get_change_count()
            self.statusBar().showMessage(
                f"⚠ {change_count} unsaved change(s) - Press Ctrl+S to save, Ctrl+Shift+R to revert"
            )
        else:
            # Only update if the message isn't a temporary one
            current_msg = self.statusBar().currentMessage()
            if current_msg.startswith("⚠") or current_msg == "Ready" or not current_msg:
                self.statusBar().showMessage("All changes saved ✓")

    def _setup_view_selector(self):
        """Setup view selector toolbar"""
        from PyQt5.QtWidgets import QHBoxLayout, QLabel, QComboBox, QWidget

        # Create toolbar widget
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(10, 5, 10, 5)

        # Add label and combobox
        toolbar_layout.addWidget(QLabel("View:"))
        self.view_selector = QComboBox()
        self.view_selector.setMinimumWidth(200)
        self.view_selector.currentIndexChanged.connect(self._on_view_changed)
        toolbar_layout.addWidget(self.view_selector)
        toolbar_layout.addStretch()

        # Add to main layout
        self.main_layout.addWidget(toolbar_widget)

        # Connect to library changes to update selector
        self.app_manager.library_changed.connect(self._update_view_selector)
        self.app_manager.project_changed.connect(self._update_view_selector)

        # Initial population
        self._update_view_selector()

    def _update_view_selector(self):
        """Update the view selector dropdown with library and projects"""
        # Block signals to avoid triggering view changes during update
        self.view_selector.blockSignals(True)

        self.view_selector.clear()

        library = self.app_manager.get_library()
        if not library:
            self.view_selector.addItem("(No library loaded)")
            self.view_selector.setEnabled(False)
            self.view_selector.blockSignals(False)
            return

        self.view_selector.setEnabled(True)

        # Add "Whole Library" option
        self.view_selector.addItem("Whole Library")

        # Add all projects
        projects = library.list_projects()
        for project_name in sorted(projects):
            self.view_selector.addItem(project_name)

        # Set current selection based on view mode
        current_view_name = self.app_manager.get_current_view_name()
        index = self.view_selector.findText(current_view_name)
        if index >= 0:
            self.view_selector.setCurrentIndex(index)

        self.view_selector.blockSignals(False)

    def _on_view_changed(self, index):
        """Handle view selector change"""
        if index < 0:
            return

        view_name = self.view_selector.currentText()

        if view_name == "Whole Library":
            self.app_manager.switch_to_library_view()
        elif view_name != "(No library loaded)":
            # Switch to project view
            self.app_manager.switch_to_project_view(view_name)

    # Menu actions
    def show_manage_projects(self):
        """Show the Manage Projects dialog"""
        from .manage_projects_dialog import ManageProjectsDialog

        if (
            not hasattr(self, "manage_projects_dialog")
            or not self.manage_projects_dialog
        ):
            self.manage_projects_dialog = ManageProjectsDialog(self.app_manager, self)

        self.manage_projects_dialog.show()
        self.manage_projects_dialog.raise_()
        self.manage_projects_dialog.activateWindow()

    def save_all(self):
        """Save library and all projects with confirmation and file moves"""
        # Check if there's a library loaded
        library = self.app_manager.get_library()
        if not library:
            self.statusBar().showMessage("No library loaded", 2000)
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
            QMessageBox.StandardButton.Save,
        )

        if reply == QMessageBox.StandardButton.Save:
            if self.app_manager.commit_all_changes():
                self.statusBar().showMessage("Saved successfully", 2000)
            else:
                self.statusBar().showMessage("Save failed", 2000)
        else:
            self.statusBar().showMessage("Save cancelled", 2000)

    def revert_all(self):
        """Revert all unsaved changes and reload from disk"""
        # Check if there's a library loaded
        library = self.app_manager.get_library()
        if not library:
            self.statusBar().showMessage("No library loaded", 2000)
            return

        # Check if there are pending changes
        pending = self.app_manager.get_pending_changes()
        if not pending.has_changes():
            QMessageBox.information(
                self, "No Changes", "There are no unsaved changes to revert."
            )
            return

        # Show confirmation dialog with change summary
        summary = pending.get_summary()
        change_count = pending.get_change_count()

        reply = QMessageBox.warning(
            self,
            "Revert Changes?",
            f"Discard {change_count} unsaved change(s) and reload from disk?\n\n{summary}\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.app_manager.revert_all_changes():
                self.statusBar().showMessage(
                    "Changes reverted - reloaded from disk", 3000
                )
            else:
                self.statusBar().showMessage("Revert failed", 2000)
        else:
            self.statusBar().showMessage("Revert cancelled", 2000)

    def refresh_from_disk(self):
        """
        Refresh from disk: scan for new files, create JSONs, and reload existing data.

        This is useful when:
        - Files were added manually to the images directory
        - Files were edited externally (e.g., video trimming)
        - Syncing with other instances
        """
        # Check if there's a library loaded
        library = self.app_manager.get_library()
        if not library:
            self.statusBar().showMessage("No library loaded", 2000)
            return

        # Check if there are pending changes - warn user
        pending = self.app_manager.get_pending_changes()
        if pending.has_changes():
            summary = pending.get_summary()
            change_count = pending.get_change_count()

            reply = QMessageBox.warning(
                self,
                "Unsaved Changes",
                f"You have {change_count} unsaved change(s):\n\n{summary}\n\n"
                "Refreshing from disk will discard these changes. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Refresh cancelled", 2000)
                return

        # First reload existing data from disk (discarding unsaved changes)
        reloaded = self.app_manager.revert_all_changes(force_reload=True)

        # Then scan for new files and add them
        new_files_count = self.app_manager.scan_and_add_new_files()

        # Update status
        if reloaded:
            # Count total images in current view
            current_view = self.app_manager.get_current_view()
            image_count = len(current_view.get_all_paths()) if current_view else 0

            # Build status message
            if new_files_count > 0:
                status_msg = f"Refreshed from disk - {image_count} total images ({new_files_count} new files added)"
            else:
                status_msg = f"Refreshed from disk - {image_count} images loaded"

            self.statusBar().showMessage(status_msg, 3000)
        else:
            self.statusBar().showMessage("Refresh failed", 2000)

    def show_welcome_screen(self):
        """Show welcome screen to open existing or create new library"""
        from .welcome_screen import WelcomeScreen

        # Create and show welcome dialog
        welcome_screen = WelcomeScreen(self.app_manager)
        if welcome_screen.exec_() == WelcomeScreen.Accepted:
            # Library was changed - update the view
            if self.app_manager.get_library():
                self.statusBar().showMessage("Library loaded", 2000)
                # Refresh current view if any
                current_view = self.app_manager.get_current_view()
                if current_view:
                    self.gallery.refresh() if hasattr(
                        self, "gallery"
                    ) and self.gallery else None

    def import_images(self):
        """Import images into library (and optionally to a project)"""
        library = self.app_manager.get_library()
        if not library:
            QMessageBox.warning(
                self,
                "No Library",
                "No library loaded. Please open or create a library first.",
            )
            return

        # Show import dialog
        from .import_dialog import ImportDialog

        dialog = ImportDialog(self, self.app_manager)
        if dialog.exec():
            count = dialog.imported_count
            self.statusBar().showMessage(f"Imported {count} images to library", 3000)

    def refresh_fuzzy_finder(self):
        """Refresh fuzzy finder tag suggestions in tag window"""
        # Refresh tag window if it exists
        if hasattr(self, "tag_window") and self.tag_window:
            self.tag_window._update_tag_suggestions()

        self.statusBar().showMessage("Fuzzy finder refreshed", 2000)

    def show_preferences(self):
        """Show preferences dialog"""
        QMessageBox.information(
            self,
            "Preferences",
            f"Preferences not yet implemented.\n\nConfig location:\n{self.app_manager.config_manager.get_config_path()}",
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
            "See README.md for details",
        )

    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About Image Tagger",
            "Image Tagger v0.2.0\n\nSimple PyQt5 application template",
        )

    def show_gallery(self):
        """Show gallery window"""
        from .gallery import Gallery

        if not hasattr(self, "gallery_window") or not self.gallery_window:
            self.gallery_window = Gallery(self.app_manager)
        self.gallery_window.show()
        self.gallery_window.raise_()
        self.gallery_window.activateWindow()

    def show_tag(self):
        """Show tag editor window"""
        from .tag_window import TagWindow

        if not hasattr(self, "tag_window") or not self.tag_window:
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
                action.triggered.connect(
                    lambda checked, name=plugin_name: self.show_plugin(name)
                )
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
                    self, "Plugin Error", f"Error loading plugin '{plugin_name}':\n{e}"
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
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
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
        if hasattr(self, "gallery_window") and self.gallery_window:
            self.gallery_window.close()
        if hasattr(self, "tag_window") and self.tag_window:
            self.tag_window.close()
        if hasattr(self, "export_window") and self.export_window:
            self.export_window.close()

        # Close all plugin windows
        for plugin_name, window in self.plugin_windows.items():
            if window:
                window.close()

        event.accept()
