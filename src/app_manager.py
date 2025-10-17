"""
Application Manager - Central data controller
"""
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal
from typing import List

from .data_models import GlobalConfig, ProjectData, ImageSelectionData, ImageData, Tag
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
        self.global_config = self.config_manager.load_config()
        self.project_data = ProjectData()
        self.image_selection = ImageSelectionData()

    # Data access
    def get_config(self) -> GlobalConfig:
        """Get global configuration"""
        return self.global_config

    def get_project(self) -> ProjectData:
        """Get current project data"""
        return self.project_data

    def get_selection(self) -> ImageSelectionData:
        """Get current selection"""
        return self.image_selection

    # Data updates
    def update_config(self, save: bool = True):
        """Update configuration and notify"""
        if save:
            self.config_manager.save_config(self.global_config)
        self.config_changed.emit()

    def update_project(self, save: bool = True):
        """Update project and notify"""
        if save:
            self.project_data.save()
        self.project_changed.emit()

    def update_selection(self):
        """Update selection and notify"""
        self.selection_changed.emit()

    def load_project(self, project_file: Path):
        """Load project from file"""
        self.project_data = ProjectData.load(project_file)

        # Add to recent projects
        project_path_str = str(project_file)
        if project_path_str not in self.global_config.recent_projects:
            self.global_config.recent_projects.insert(0, project_path_str)
            self.global_config.recent_projects = self.global_config.recent_projects[:self.global_config.max_recent_projects]
            self.config_manager.save_config(self.global_config)

        # Clear filter (None = no filter, shows all images)
        self.image_selection.filtered_images = None
        image_paths = self.project_data.get_all_absolute_image_paths()
        if image_paths:
            self.image_selection.set_active(image_paths[0])

        # Notify
        self.config_changed.emit()
        self.project_changed.emit()
        self.selection_changed.emit()

    def save_project(self):
        """Save current project"""
        self.project_data.save()

    def get_all_tags_in_project(self) -> List[str]:
        """Get all unique tags in the project in category:value format"""
        tags = set()
        for img_path in self.project_data.get_all_absolute_image_paths():
            json_path = self.project_data.get_image_json_path(img_path)
            if json_path.exists():
                img_data = ImageData.load(json_path)
                for tag in img_data.tags:
                    tags.add(str(tag))
        return sorted(list(tags))

    def load_image_data(self, image_path: Path) -> ImageData:
        """Load image data from JSON file"""
        json_path = self.project_data.get_image_json_path(image_path)
        return ImageData.load(json_path)

    def save_image_data(self, image_path: Path, image_data: ImageData):
        """Save image data to JSON file"""
        json_path = self.project_data.get_image_json_path(image_path)
        image_data.save(json_path)

    def remove_images_from_project(self, image_paths: List[Path]) -> int:
        """
        Remove images from the project

        Args:
            image_paths: List of image paths to remove

        Returns:
            Number of images successfully removed
        """
        count = 0
        for img_path in image_paths:
            if self.project_data.remove_image(img_path):
                count += 1
                # Remove from selection if present
                if img_path in self.image_selection.selected_images:
                    self.image_selection.selected_images.remove(img_path)
                # Clear active image if it was removed
                if self.image_selection.active_image == img_path:
                    self.image_selection.active_image = None

        # Save project
        if count > 0:
            self.project_data.save()
            # Update filtered images if a filter is applied
            if self.image_selection.filtered_images is not None:
                self.image_selection.filtered_images = [
                    img for img in self.image_selection.filtered_images
                    if img not in image_paths
                ]

        return count