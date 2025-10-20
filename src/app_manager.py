"""
Application Manager - Central data controller
"""
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal, QUrl
from PyQt5.QtWidgets import QFileDialog, QWidget
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
        self._plugins_with_unsaved_changes = set()  # Track plugins with unsaved changes

        # ImageData cache - prevents re-reading JSON files for recently accessed images
        self._image_data_cache = {}  # {image_path: ImageData}
        self._cache_max_size = 1000  # Keep up to 1000 most recently used images in cache

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
        return self.filtered_view if self.filtered_view is not None else self.project_data.image_list

    def set_filtered_view(self, filtered_list: Optional[ImageList]):
        """Set the filtered view (None to clear filter)"""
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

        # Clear image data cache (new project, old cache is invalid)
        self._image_data_cache.clear()

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

        # Invalidate cache for modified images (they're being written to disk)
        for img_path in self.pending_changes.get_modified_images().keys():
            if img_path in self._image_data_cache:
                del self._image_data_cache[img_path]

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
        """Load image data (from pending changes if modified, otherwise from cache or disk)"""
        # Check if there's a pending change first (highest priority)
        modified_images = self.pending_changes.get_modified_images()
        if image_path in modified_images:
            return modified_images[image_path]

        # Check cache second
        if image_path in self._image_data_cache:
            return self._image_data_cache[image_path]

        # Load from disk and cache
        if self.project_data.image_list is not None:
            image_data = self.project_data.image_list.get_image_data(image_path)
        else:
            # Fallback to direct load
            json_path = self.project_data.get_image_json_path(image_path)
            image_data = ImageData.load(json_path)

        # Add to cache with size limit
        self._image_data_cache[image_path] = image_data
        if len(self._image_data_cache) > self._cache_max_size:
            # Remove oldest entry (first item in dict - Python 3.7+ maintains insertion order)
            oldest_key = next(iter(self._image_data_cache))
            del self._image_data_cache[oldest_key]

        return image_data

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
        # Invalidate cache for removed images
        for img_path in image_paths:
            if img_path in self._image_data_cache:
                del self._image_data_cache[img_path]

        count = 0
        if self.project_data.image_list is not None:
            count = self.project_data.image_list.remove_images(image_paths)

        # Track project modification (deferred save)
        if count > 0:
            self.pending_changes.mark_project_modified()

        return count

    # Plugin change tracking
    def notify_plugin_changes(self, plugin, has_changes: bool):
        """
        Notify app manager that a plugin has unsaved changes

        Args:
            plugin: The plugin instance
            has_changes: True if plugin has unsaved changes, False otherwise
        """
        if has_changes:
            self._plugins_with_unsaved_changes.add(plugin)
        else:
            self._plugins_with_unsaved_changes.discard(plugin)

    def has_any_plugin_unsaved_changes(self) -> bool:
        """Check if any plugin has unsaved changes"""
        return len(self._plugins_with_unsaved_changes) > 0

    def get_plugins_with_unsaved_changes(self) -> List:
        """Get list of plugins with unsaved changes"""
        return list(self._plugins_with_unsaved_changes)

    # File dialog helpers with persistence
    def get_existing_directory(
        self,
        parent: QWidget,
        caption: str,
        directory_type: str,
        default_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Show directory picker with persistent last directory and sidebar URLs

        Args:
            parent: Parent widget
            caption: Dialog caption
            directory_type: Type of directory ('project', 'import_source', 'import_dest', 'export')
            default_dir: Default directory if no last directory is saved

        Returns:
            Selected directory path or None if cancelled
        """
        # Get starting directory
        last_dir_map = {
            'project': self.global_config.last_directory_project,
            'import_source': self.global_config.last_directory_import_source,
            'import_dest': self.global_config.last_directory_import_dest,
            'export': self.global_config.last_directory_export
        }

        start_dir = last_dir_map.get(directory_type, "")
        if not start_dir or not Path(start_dir).exists():
            start_dir = str(default_dir) if default_dir else str(Path.home())

        # Create dialog instance (not static method) to enable sidebar URLs
        dialog = QFileDialog(parent, caption, start_dir)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)

        # Restore sidebar URLs (pinned shortcuts)
        if self.global_config.file_dialog_sidebar_urls:
            sidebar_urls = [QUrl.fromLocalFile(url) for url in self.global_config.file_dialog_sidebar_urls]
            dialog.setSidebarUrls(sidebar_urls)

        # Show dialog
        if dialog.exec_() != QFileDialog.Accepted:
            return None

        # Get selected directory
        selected_dirs = dialog.selectedFiles()
        if not selected_dirs:
            return None

        selected_path = Path(selected_dirs[0])

        # Save last directory and sidebar URLs
        if directory_type == 'project':
            self.global_config.last_directory_project = str(selected_path)
        elif directory_type == 'import_source':
            self.global_config.last_directory_import_source = str(selected_path)
        elif directory_type == 'import_dest':
            self.global_config.last_directory_import_dest = str(selected_path)
        elif directory_type == 'export':
            self.global_config.last_directory_export = str(selected_path)

        # Save sidebar URLs
        sidebar_urls = dialog.sidebarUrls()
        self.global_config.file_dialog_sidebar_urls = [url.toLocalFile() for url in sidebar_urls if url.isLocalFile()]

        self.config_manager.save_config(self.global_config)

        return selected_path

    def get_save_filename(
        self,
        parent: QWidget,
        caption: str,
        default_name: str,
        file_filter: str
    ) -> Optional[Path]:
        """
        Show save file dialog with persistent last directory and sidebar URLs

        Args:
            parent: Parent widget
            caption: Dialog caption
            default_name: Default filename
            file_filter: File filter string

        Returns:
            Selected file path or None if cancelled
        """
        # Get starting directory
        start_dir = self.global_config.last_directory_project
        if not start_dir or not Path(start_dir).exists():
            start_dir = str(Path.home())

        # Combine directory with default filename
        start_path = str(Path(start_dir) / default_name)

        # Create dialog instance
        dialog = QFileDialog(parent, caption, start_path, file_filter)
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setFileMode(QFileDialog.AnyFile)

        # Restore sidebar URLs
        if self.global_config.file_dialog_sidebar_urls:
            sidebar_urls = [QUrl.fromLocalFile(url) for url in self.global_config.file_dialog_sidebar_urls]
            dialog.setSidebarUrls(sidebar_urls)

        # Show dialog
        if dialog.exec_() != QFileDialog.Accepted:
            return None

        # Get selected file
        selected_files = dialog.selectedFiles()
        if not selected_files:
            return None

        selected_path = Path(selected_files[0])

        # Save last directory and sidebar URLs
        self.global_config.last_directory_project = str(selected_path.parent)

        # Save sidebar URLs
        sidebar_urls = dialog.sidebarUrls()
        self.global_config.file_dialog_sidebar_urls = [url.toLocalFile() for url in sidebar_urls if url.isLocalFile()]

        self.config_manager.save_config(self.global_config)

        return selected_path

    def get_open_filename(
        self,
        parent: QWidget,
        caption: str,
        file_filter: str
    ) -> Optional[Path]:
        """
        Show open file dialog with persistent last directory and sidebar URLs

        Args:
            parent: Parent widget
            caption: Dialog caption
            file_filter: File filter string

        Returns:
            Selected file path or None if cancelled
        """
        # Get starting directory
        start_dir = self.global_config.last_directory_project
        if not start_dir or not Path(start_dir).exists():
            start_dir = str(Path.home())

        # Create dialog instance
        dialog = QFileDialog(parent, caption, start_dir, file_filter)
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setFileMode(QFileDialog.ExistingFile)

        # Restore sidebar URLs
        if self.global_config.file_dialog_sidebar_urls:
            sidebar_urls = [QUrl.fromLocalFile(url) for url in self.global_config.file_dialog_sidebar_urls]
            dialog.setSidebarUrls(sidebar_urls)

        # Show dialog
        if dialog.exec_() != QFileDialog.Accepted:
            return None

        # Get selected file
        selected_files = dialog.selectedFiles()
        if not selected_files:
            return None

        selected_path = Path(selected_files[0])

        # Save last directory and sidebar URLs
        self.global_config.last_directory_project = str(selected_path.parent)

        # Save sidebar URLs
        sidebar_urls = dialog.sidebarUrls()
        self.global_config.file_dialog_sidebar_urls = [url.toLocalFile() for url in sidebar_urls if url.isLocalFile()]

        self.config_manager.save_config(self.global_config)

        return selected_path