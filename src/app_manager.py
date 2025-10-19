"""
Application Manager - Central data controller
"""
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal
from typing import List, Optional

from .data_models import GlobalConfig, ProjectData, ImageData, TagList, ImageList, PendingChanges
from .config_manager import ConfigManager


class AppManager(QObject):
    """Central manager for application data and state"""

    # Signals for data changes
    config_changed = pyqtSignal()
    project_changed = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.config_manager = ConfigManager()
        self.global_config = self.config_manager.load_config()
        self.project_data = ProjectData()
        self.tag_list: TagList = TagList()
        self.pending_changes = PendingChanges()
        self.filtered_view: Optional[ImageList] = None  # Filtered ImageList view

    # Data access
    def get_config(self) -> GlobalConfig:
        """Get global configuration"""
        return self.global_config

    def get_project(self) -> ProjectData:
        """Get current project data"""
        return self.project_data

    def get_image_list(self) -> Optional[ImageList]:
        """Get image list"""
        return self.project_data.image_list

    def get_current_view(self) -> Optional[ImageList]:
        """Get current view (filtered if exists, otherwise main image list)"""
        result = self.filtered_view if self.filtered_view is not None else self.project_data.image_list
        print(f"\n=== get_current_view() DEBUG ===")
        print(f"self.filtered_view is None: {self.filtered_view is None}")
        if result is not None:
            print(f"Returning view with {len(result.get_all_paths())} images")
            print(f"View type: {type(result).__name__}")
            print(f"Image names: {[p.name for p in result.get_all_paths()]}")
        else:
            print("Returning None")
        print("=" * 50 + "\n")
        return result

    def set_filtered_view(self, filtered_list: Optional[ImageList]):
        """Set the filtered view (None to clear filter)"""
        print(f"\n=== set_filtered_view() DEBUG ===")
        if filtered_list is not None:  # Fixed: explicitly check for None, not truthiness
            print(f"Setting filtered view with {len(filtered_list.get_all_paths())} images")
            print(f"Image names: {[p.name for p in filtered_list.get_all_paths()]}")
        else:
            print("Clearing filtered view (setting to None)")
        print("=" * 50 + "\n")

        self.filtered_view = filtered_list
        self.project_changed.emit()

    def get_tag_list(self) -> TagList:
        """Get tag list"""
        return self.tag_list

    def get_pending_changes(self) -> PendingChanges:
        """Get pending changes tracker"""
        return self.pending_changes

    # Data updates
    def update_config(self, save: bool = True):
        """Update configuration and notify"""
        if save:
            self.config_manager.save_config(self.global_config)
        self.config_changed.emit()

    def update_project(self, save: bool = True):
        """Update project and notify (deferred save by default)"""
        if save:
            # Track project modification (deferred)
            self.pending_changes.mark_project_modified()
        self.project_changed.emit()

    def load_project(self, project_file: Path):
        """Load project from file"""
        self.project_data = ProjectData.load(project_file)

        # Clear any pending changes from previous project
        self.pending_changes.clear()

        # Clear filtered view
        self.filtered_view = None

        # Add to recent projects
        project_path_str = str(project_file)
        if project_path_str not in self.global_config.recent_projects:
            self.global_config.recent_projects.insert(0, project_path_str)
            self.global_config.recent_projects = self.global_config.recent_projects[:self.global_config.max_recent_projects]
            self.config_manager.save_config(self.global_config)

        # Build TagList from ImageList
        if self.project_data.image_list is not None:
            self.tag_list.build_from_imagelist(self.project_data.image_list)
            # Set active image to first image
            image_paths = self.project_data.image_list.get_all_paths()
            if image_paths:
                self.project_data.image_list.set_active(image_paths[0])

        # Notify
        self.config_changed.emit()
        self.project_changed.emit()

    def save_project(self):
        """Mark project as needing save (deferred)"""
        self.pending_changes.mark_project_modified()

    def commit_all_changes(self) -> bool:
        """
        Commit all pending changes to disk

        Returns:
            True if changes were committed, False if cancelled or error
        """
        if not self.pending_changes.has_changes():
            return True

        # Save all modified image data
        for img_path, img_data in self.pending_changes.get_modified_images().items():
            if self.project_data.image_list is not None:
                self.project_data.image_list.save_image_data(img_path, img_data)
            else:
                json_path = self.project_data.get_image_json_path(img_path)
                img_data.save(json_path)

        # Save project data
        self.project_data.save()

        # Clear pending changes
        self.pending_changes.clear()

        return True

    def load_image_data(self, image_path: Path) -> ImageData:
        """Load image data (from pending changes if modified, otherwise from disk)"""
        # Check if there's a pending change first
        modified_images = self.pending_changes.get_modified_images()
        if image_path in modified_images:
            return modified_images[image_path]

        # Load from disk
        if self.project_data.image_list is not None:
            return self.project_data.image_list.get_image_data(image_path)
        # Fallback to direct load
        json_path = self.project_data.get_image_json_path(image_path)
        return ImageData.load(json_path)

    def save_image_data(self, image_path: Path, image_data: ImageData):
        """Track image data changes (deferred save - does not write to disk)"""
        # Track the change
        self.pending_changes.mark_image_modified(image_path, image_data)

        # Update TagList with any new tags
        for tag in image_data.tags:
            self.tag_list.add_tag(tag.category, tag.value)

    def get_all_tags_in_project(self) -> List[str]:
        """Get all tags for fuzzy search (for backward compatibility)"""
        return self.tag_list.get_all_tags()

    def rebuild_tag_list(self):
        """Rebuild the tag list from all images in the project (including pending changes)"""
        self.tag_list.clear()
        if self.project_data.image_list is not None:
            for img_path in self.project_data.image_list:
                img_data = self.load_image_data(img_path)  # Uses pending changes if available
                for tag in img_data.tags:
                    self.tag_list.add_tag(tag.category, tag.value)

    def remove_images_from_project(self, image_paths: List[Path]) -> int:
        """
        Remove images from the project (deferred save)

        Args:
            image_paths: List of image paths to remove

        Returns:
            Number of images successfully removed
        """
        count = 0
        if self.project_data.image_list is not None:
            count = self.project_data.image_list.remove_images(image_paths)

        # Track project modification (deferred save)
        if count > 0:
            self.pending_changes.mark_project_modified()

        return count