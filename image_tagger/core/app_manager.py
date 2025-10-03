"""
Application Manager - Central controller for the application
Manages data models, window instances, and tool registration
"""
from typing import Dict, List, Optional, Type
from pathlib import Path
from PyQt5.QtWidgets import QMainWindow, QWidget
from PyQt5.QtCore import QObject, pyqtSignal

from .data_models import AppConfig, ProjectData, ImageSelectionData
from .tool_registry import ToolRegistry
from image_tagger.utils.config_manager import ConfigManager
from image_tagger.windows.main_window import MainWindow


class AppManager(QObject):
    """
    Central manager for the application
    - Manages shared data models
    - Handles window lifecycle
    - Provides data access to all tools
    """
    
    # Signals for data changes
    config_changed = pyqtSignal()
    project_changed = pyqtSignal()
    selection_changed = pyqtSignal()
    
    def __init__(self):
        super().__init__()

        # Config manager for persistence
        self.config_manager = ConfigManager()

        # Initialize data models
        self.app_config = self._load_app_config()
        self.project_data = ProjectData()
        self.image_selection = ImageSelectionData()

        # Window management
        self.main_window: Optional[MainWindow] = None
        self.tool_windows: Dict[str, QWidget] = {}

        # Tool registry
        self.tool_registry = ToolRegistry(self)

        # Auto-discover and register tools
        self._discover_tools()

    def _load_app_config(self) -> AppConfig:
        """Load app configuration from disk or create new"""
        config_data = self.config_manager.load_config()
        if config_data:
            return AppConfig(**config_data)
        return AppConfig()

    def _save_app_config(self):
        """Save app configuration to disk"""
        config_dict = {
            'theme': self.app_config.theme,
            'window_mode': self.app_config.window_mode,
            'recent_projects': self.app_config.recent_projects,
            'default_image_extensions': self.app_config.default_image_extensions,
            'autosave_interval': self.app_config.autosave_interval,
            'max_recent_projects': self.app_config.max_recent_projects,
            'custom_settings': self.app_config.custom_settings
        }
        self.config_manager.save_config(config_dict)
    
    def _discover_tools(self):
        """Auto-discover and register available tools"""
        self.tool_registry.discover_tools()
    
    def show_main_window(self):
        """Create and show the main window"""
        if not self.main_window:
            self.main_window = MainWindow(self)
        self.main_window.show()
    
    def open_tool(self, tool_id: str):
        """Open a tool window by its ID"""
        if tool_id in self.tool_windows:
            # Bring existing window to front
            window = self.tool_windows[tool_id]
            window.show()
            window.raise_()
            window.activateWindow()
        else:
            # Create new tool window
            tool_class = self.tool_registry.get_tool(tool_id)
            if tool_class:
                window = tool_class(self)
                self.tool_windows[tool_id] = window
                window.show()
    
    def close_tool(self, tool_id: str):
        """Close and cleanup a tool window"""
        if tool_id in self.tool_windows:
            window = self.tool_windows.pop(tool_id)
            window.close()
    
    # Data access methods for tools
    def get_config(self) -> AppConfig:
        """Get the global app configuration"""
        return self.app_config
    
    def get_project(self) -> ProjectData:
        """Get the current project data"""
        return self.project_data
    
    def get_selection(self) -> ImageSelectionData:
        """Get the current image selection"""
        return self.image_selection
    
    def update_config(self, config: AppConfig, save: bool = True):
        """
        Update app configuration and notify listeners

        Args:
            config: New configuration
            save: If True, save config to disk immediately
        """
        self.app_config = config
        if save:
            self._save_app_config()
        self.config_changed.emit()

    def update_project(self, project: ProjectData, save: bool = True):
        """
        Update project data and notify listeners

        Args:
            project: New project data
            save: If True, save project to tagger.json immediately
        """
        self.project_data = project
        if save:
            self.project_data.save()
        self.project_changed.emit()

    def update_selection(self, selection: ImageSelectionData):
        """Update image selection and notify listeners"""
        self.image_selection = selection
        self.selection_changed.emit()

    def load_project(self, project_file: Path):
        """
        Load a project from tagger.json file

        Args:
            project_file: Path to tagger.json
        """
        self.project_data = ProjectData.load(project_file)

        # Add to recent projects
        project_path_str = str(project_file)
        if project_path_str not in self.app_config.recent_projects:
            self.app_config.recent_projects.insert(0, project_path_str)
            # Keep only max recent projects
            self.app_config.recent_projects = self.app_config.recent_projects[:self.app_config.max_recent_projects]
            self._save_app_config()

        # Load images into selection
        image_paths = self.project_data.get_all_absolute_image_paths()
        if image_paths:
            self.image_selection.select_multiple(image_paths)

        # Notify listeners
        self.config_changed.emit()
        self.project_changed.emit()
        self.selection_changed.emit()

    def save_project(self):
        """Save current project to disk"""
        self.project_data.save()