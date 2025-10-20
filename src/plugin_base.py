"""
Plugin Base Classes - Foundation for the plugin system
"""
from typing import List, Optional
from pathlib import Path
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent


class PluginBase:
    """Base class for all plugins"""

    def __init__(self):
        self.name: str = "Unnamed Plugin"
        self.description: str = "No description"
        self.shortcut: Optional[str] = None
        self.app_manager = None
        self._has_unsaved_changes: bool = False

    def execute(self, app_manager, selected_images: List[Path]) -> None:
        """
        Execute plugin on selected images

        Subclasses must override this method.

        Args:
            app_manager: AppManager instance for accessing project data
            selected_images: List of image paths to process
        """
        raise NotImplementedError("Plugin must implement execute() method")

    def get_name(self) -> str:
        """Get plugin display name"""
        return self.name

    def get_description(self) -> str:
        """Get plugin description"""
        return self.description

    def get_shortcut(self) -> Optional[str]:
        """Get plugin keyboard shortcut"""
        return self.shortcut

    def has_unsaved_changes(self) -> bool:
        """Check if plugin has unsaved changes"""
        return self._has_unsaved_changes

    def set_unsaved_changes(self, has_changes: bool) -> None:
        """
        Mark plugin as having unsaved changes

        Args:
            has_changes: True if plugin has unsaved changes, False otherwise
        """
        self._has_unsaved_changes = has_changes

        # Notify app_manager if available
        if self.app_manager and hasattr(self.app_manager, 'notify_plugin_changes'):
            self.app_manager.notify_plugin_changes(self, has_changes)


class PluginWindow(QWidget, PluginBase):
    """Base class for plugins with UI windows with automatic scroll support"""

    def __init__(self, app_manager, parent=None):
        QWidget.__init__(self, parent)
        PluginBase.__init__(self)

        self.app_manager = app_manager

        self.setWindowTitle(self.name)
        self.setMinimumSize(400, 300)
        self.resize(600, 500)

        # Create scroll area for content
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Create container widget for scroll area
        self.scroll_content = QWidget()
        self.scroll_area.setWidget(self.scroll_content)

        # Main layout for the window
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.scroll_area)

    def execute(self, app_manager, selected_images: List[Path]) -> None:
        """
        Default execute for window-based plugins - shows the window

        Subclasses can override this or just implement their own UI logic
        """
        self.show()
        self.raise_()
        self.activateWindow()

    def get_selected_images(self) -> List[Path]:
        """
        Helper method to get selected images from current view

        Returns:
            List of selected image paths, or active image if no selection
        """
        current_view = self.app_manager.get_current_view()
        if current_view is not None:
            return current_view.get_working_images()
        return []

    def get_all_images(self) -> List[Path]:
        """
        Helper method to get all images in current view

        Returns:
            List of all image paths in current view (filtered or main)
        """
        current_view = self.app_manager.get_current_view()
        if current_view is not None:
            return current_view.get_all_paths()
        return []

    def setup_window(self):
        """
        Setup basic window properties
        Override this to customize window setup
        """
        layout = QVBoxLayout(self)

        # Add a default info label
        info_label = QLabel(f"{self.name}\n{self.description}")
        info_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(info_label)

        return layout

    def save_changes(self) -> bool:
        """
        Save plugin changes to project

        Plugins should override this method to implement their save logic.

        Returns:
            True if save was successful, False otherwise
        """
        # Default implementation does nothing
        return True

    def closeEvent(self, event: QCloseEvent):
        """Handle window close event - prompt if unsaved changes exist"""
        if self.has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"{self.name} has unsaved changes.\n\n"
                "Do you want to save your changes before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )

            if reply == QMessageBox.Save:
                # Try to save changes
                if self.save_changes():
                    # Successfully saved, clear flag and accept close
                    self.set_unsaved_changes(False)
                    event.accept()
                else:
                    # Save failed, don't close
                    event.ignore()
            elif reply == QMessageBox.Discard:
                # Discard changes and close
                self.set_unsaved_changes(False)
                event.accept()
            else:  # Cancel
                # Don't close
                event.ignore()
        else:
            # No unsaved changes, just close
            event.accept()
