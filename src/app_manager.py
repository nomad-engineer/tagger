"""
Application Manager - Central data controller
"""
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal

from .data_models import AppConfig, ProjectData, ImageSelectionData
from .config_manager import ConfigManager


class AppManager(QObject):
    """Central manager for application data and state"""

    # Signals for data changes
    config_changed = pyqtSignal()
    project_changed = pyqtSignal()
    selection_changed = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.config_manager = ConfigManager()
        self.app_config = self._load_config()
        self.project_data = ProjectData()
        self.image_selection = ImageSelectionData()

    def _load_config(self) -> AppConfig:
        """Load app configuration"""
        config_data = self.config_manager.load_config()
        if config_data:
            return AppConfig(**config_data)
        return AppConfig()

    def _save_config(self):
        """Save app configuration"""
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

    # Data access
    def get_config(self) -> AppConfig:
        """Get app configuration"""
        return self.app_config

    def get_project(self) -> ProjectData:
        """Get current project data"""
        return self.project_data

    def get_selection(self) -> ImageSelectionData:
        """Get current selection"""
        return self.image_selection

    # Data updates
    def update_config(self, config: AppConfig = None, save: bool = True):
        """Update configuration and notify"""
        if config:
            self.app_config = config
        if save:
            self._save_config()
        self.config_changed.emit()

    def update_project(self, project: ProjectData = None, save: bool = True):
        """Update project and notify"""
        if project:
            self.project_data = project
        if save:
            self.project_data.save()
        self.project_changed.emit()

    def update_selection(self, selection: ImageSelectionData = None):
        """Update selection and notify"""
        if selection:
            self.image_selection = selection
        self.selection_changed.emit()

    def load_project(self, project_file: Path):
        """Load project from file"""
        self.project_data = ProjectData.load(project_file)

        # Add to recent projects
        project_path_str = str(project_file)
        if project_path_str not in self.app_config.recent_projects:
            self.app_config.recent_projects.insert(0, project_path_str)
            self.app_config.recent_projects = self.app_config.recent_projects[:self.app_config.max_recent_projects]
            self._save_config()

        # Load images into selection
        image_paths = self.project_data.get_all_absolute_image_paths()
        if image_paths:
            self.image_selection.select_multiple(image_paths)

        # Notify
        self.config_changed.emit()
        self.project_changed.emit()
        self.selection_changed.emit()

    def save_project(self):
        """Save current project"""
        self.project_data.save()