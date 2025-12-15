"""
Application Manager - Central data controller
"""

from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal, QUrl
from PyQt5.QtWidgets import QFileDialog, QWidget
from typing import List, Optional

from .data_models import (
    GlobalConfig,
    ProjectData,
    ImageData,
    TagList,
    ImageList,
    PendingChanges,
    ImageLibrary,
)
from .config_manager import ConfigManager
from .repository import FileSystemRepository, DatabaseRepository, CacheRepository
from .database import Database


class AppManager(QObject):
    """Central manager for application data and state"""

    # Signals for data changes
    config_changed = pyqtSignal()
    project_changed = pyqtSignal()
    library_changed = pyqtSignal()  # Emitted when library or active view changes
    active_image_changed = pyqtSignal()  # Emitted when active image changes
    image_data_changed = pyqtSignal(
        Path
    )  # Emitted when image data (tags, caption) changes

    def __init__(self):
        super().__init__()

        self.config_manager = ConfigManager()
        self.global_config = self.config_manager.load_config()

        # Library and projects
        self.current_library: Optional[ImageLibrary] = None
        self.current_project: Optional[ProjectData] = None
        self.current_view_mode: str = "library"  # "library" or "project"

        # Legacy support
        self.project_data = ProjectData()  # Keep for backward compatibility

        self.tag_list: TagList = TagList()
        self.pending_changes = PendingChanges()
        self.filtered_view: Optional[ImageList] = None  # Filtered ImageList view
        self.current_filter_expression: str = ""  # Track current filter expression
        self._plugins_with_unsaved_changes = set()  # Track plugins with unsaved changes

        # ImageData cache - prevents re-reading JSON files for recently accessed images
        self._image_data_cache = {}  # {image_path: ImageData}
        self._cache_max_size = (
            1000  # Keep up to 1000 most recently used images in cache
        )

        # Repository instances (initialized when library is loaded)
        self.fs_repo: Optional[FileSystemRepository] = None
        self.db_repo: Optional[DatabaseRepository] = None
        self.cache_repo: Optional[CacheRepository] = None

    # Data access
    def get_config(self) -> GlobalConfig:
        """Get global configuration"""
        return self.global_config

    def get_library(self) -> Optional[ImageLibrary]:
        """Get current library"""
        return self.current_library

    def get_project(self) -> ProjectData:
        """Get current project data (returns current_project or legacy project_data)"""
        return self.current_project if self.current_project else self.project_data

    def get_image_list(self) -> Optional[ImageList]:
        """Get image list (based on current view mode)"""
        if self.current_view_mode == "library" and self.current_library:
            return self.current_library.library_image_list
        elif self.current_view_mode == "project" and self.current_project:
            return self.current_project.image_list
        else:
            # Legacy fallback
            return self.project_data.image_list

    def get_current_view(self) -> Optional[ImageList]:
        """Get current view (filtered if exists, otherwise main image list based on mode)"""
        return (
            self.filtered_view
            if self.filtered_view is not None
            else self.get_image_list()
        )

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

    # Library management
    def load_library(self, library_file: Path):
        """Load a library from file"""
        self.current_library = ImageLibrary.load(library_file)

        # Initialize repositories
        library_dir = library_file.parent
        self.fs_repo = FileSystemRepository(library_dir)
        self.cache_repo = CacheRepository(
            library_dir, self.global_config.thumbnail_size
        )

        # Initialize database repository
        db_path = library_dir / "library.db"
        if not db_path.exists():
            # Database doesn't exist - will need to rebuild
            self._check_and_rebuild_database(library_dir, db_path)

        self.db_repo = DatabaseRepository(db_path)
        try:
            self.db_repo.connect()
        except Exception as e:
            print(f"Error connecting to database: {e}")
            # Try rebuilding
            self._check_and_rebuild_database(library_dir, db_path)
            self.db_repo = DatabaseRepository(db_path)
            self.db_repo.connect()

        # Clear any pending changes from previous library
        self.pending_changes.clear()

        # Clear filtered view
        self.filtered_view = None

        # Clear image data cache
        self._image_data_cache.clear()

        # Set view mode to library
        self.current_view_mode = "library"
        self.current_project = None

        # Add to recent libraries
        library_path_str = str(library_file)
        if library_path_str not in self.global_config.recent_libraries:
            self.global_config.recent_libraries.insert(0, library_path_str)
            self.global_config.recent_libraries = self.global_config.recent_libraries[
                : self.global_config.max_recent_libraries
            ]
            self.config_manager.save_config(self.global_config)

        # Build TagList from library ImageList
        if self.current_library.library_image_list is not None:
            self.tag_list.build_from_imagelist(self.current_library.library_image_list)
            # Connect active_changed signal to propagate changes
            self.current_library.library_image_list.active_changed.connect(
                lambda: self.active_image_changed.emit()
            )
            # Set active image to first image
            image_paths = self.current_library.library_image_list.get_all_paths()
            if image_paths:
                self.current_library.library_image_list.set_active(image_paths[0])

        # Notify
        self.config_changed.emit()
        self.library_changed.emit()
        self.project_changed.emit()

    def _check_and_rebuild_database(self, library_dir: Path, db_path: Path):
        """Check if database needs rebuilding and prompt user"""
        from PyQt5.QtWidgets import QMessageBox, QProgressDialog
        from PyQt5.QtCore import Qt

        # Always prompt user before rebuilding
        reply = QMessageBox.question(
            None,
            "Rebuild Database",
            "Database missing or corrupted. Rebuild from JSON files?\n\n"
            "This may take several minutes for large libraries.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply != QMessageBox.StandardButton.Yes:
            # User declined - create empty database
            db = Database(db_path)
            db.connect()
            db.create_schema()
            db.set_schema_version(1)
            db.close()
            return

        # Rebuild database with progress dialog
        progress = QProgressDialog(
            "Rebuilding database from files...", "Cancel", 0, 100, None
        )
        progress.setWindowTitle("Database Rebuild")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        try:
            # Create new database
            db = Database(db_path)
            db.connect()
            db.create_schema()
            db.set_schema_version(1)

            # Scan JSON files
            images_dir = library_dir / "images"
            json_files = list(images_dir.glob("*.json"))
            total = len(json_files)

            progress.setMaximum(total)

            # Create temporary repository for rebuilding
            temp_db_repo = DatabaseRepository(db_path)
            temp_db_repo.db = db

            for i, json_path in enumerate(json_files):
                if progress.wasCanceled():
                    break

                try:
                    # Load media data from JSON
                    media_hash = json_path.stem
                    media_data = (
                        self.fs_repo.load_media_data(media_hash)
                        if self.fs_repo
                        else None
                    )

                    if media_data:
                        # Insert into database
                        temp_db_repo.upsert_media(media_hash, media_data)

                except Exception as e:
                    print(f"Error rebuilding {json_path}: {e}")

                progress.setValue(i + 1)

            db.close()
            progress.close()

            if not progress.wasCanceled():
                QMessageBox.information(
                    None,
                    "Rebuild Complete",
                    f"Database rebuilt successfully.\n{total} media items processed.",
                )

        except Exception as e:
            progress.close()
            QMessageBox.critical(
                None, "Rebuild Failed", f"Failed to rebuild database: {e}"
            )

    def create_library(self, library_dir: Path, library_name: str):
        """Create a new library"""
        self.current_library = ImageLibrary.create_new(library_dir, library_name)

        # Initialize repositories
        self.fs_repo = FileSystemRepository(library_dir)
        self.cache_repo = CacheRepository(
            library_dir, self.global_config.thumbnail_size
        )

        # Create database immediately for new library
        db_path = library_dir / "library.db"
        db = Database(db_path)
        db.connect()
        db.create_schema()
        db.set_schema_version(1)
        db.close()

        # Initialize database repository
        self.db_repo = DatabaseRepository(db_path)
        self.db_repo.connect()

        # Clear state
        self.pending_changes.clear()
        self.filtered_view = None
        self._image_data_cache.clear()
        self.current_view_mode = "library"
        self.current_project = None

        # Add to recent libraries
        library_file = library_dir / "library.json"
        library_path_str = str(library_file)
        if library_path_str not in self.global_config.recent_libraries:
            self.global_config.recent_libraries.insert(0, library_path_str)
            self.global_config.recent_libraries = self.global_config.recent_libraries[
                : self.global_config.max_recent_libraries
            ]
            self.config_manager.save_config(self.global_config)

        # Initialize tag list
        self.tag_list.clear()

        # Notify
        self.config_changed.emit()
        self.library_changed.emit()
        self.project_changed.emit()

    def switch_to_library_view(self):
        """Switch to viewing the whole library"""
        if not self.current_library:
            return

        self.current_view_mode = "library"
        self.current_project = None
        self.filtered_view = None

        # Rebuild tag list from library
        if self.current_library.library_image_list:
            self.tag_list.build_from_imagelist(self.current_library.library_image_list)

        self.library_changed.emit()
        self.project_changed.emit()

    def switch_to_project_view(self, project_name: str):
        """Switch to viewing a specific project"""
        if not self.current_library:
            return

        # Get project file from library
        project_file = self.current_library.get_project_file(project_name)
        if not project_file or not project_file.exists():
            return

        # Load project with library's images directory
        images_dir = self.current_library.get_images_directory()
        self.current_project = ProjectData.load(project_file, images_dir)
        self.current_view_mode = "project"
        self.filtered_view = None

        # Rebuild tag list from project
        if self.current_project.image_list:
            self.tag_list.build_from_imagelist(self.current_project.image_list)
            # Connect active_changed signal to propagate changes
            self.current_project.image_list.active_changed.connect(
                lambda: self.active_image_changed.emit()
            )
            # Set active image to first image
            image_paths = self.current_project.image_list.get_all_paths()
            if image_paths:
                self.current_project.image_list.set_active(image_paths[0])

        self.library_changed.emit()
        self.project_changed.emit()

    def get_current_view_name(self) -> str:
        """Get the name of the current view"""
        if self.current_view_mode == "library":
            return "Whole Library"
        elif self.current_project:
            return self.current_project.project_name
        return "No View"

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
        # Determine library images directory to ensure correct relative path calculation
        library_images_dir = None
        if self.current_library:
            library_images_dir = self.current_library.get_images_directory()

        self.project_data = ProjectData.load(project_file, library_images_dir)

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
            self.global_config.recent_projects = self.global_config.recent_projects[
                : self.global_config.max_recent_projects
            ]
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

        try:
            # Handle library changes
            library = self.get_library()
            if library and library.library_file:
                # Move removed images to deleted folder
                removed_images = self.pending_changes.get_removed_images()
                if removed_images:
                    self._move_removed_images_to_deleted_folder(removed_images)

                # Save library data
                library.save()

                # Save modified image data when in library view mode
                if self.current_view_mode == "library":
                    # Invalidate cache for modified images (they're being written to disk)
                    for img_path in self.pending_changes.get_modified_images().keys():
                        if img_path in self._image_data_cache:
                            del self._image_data_cache[img_path]

                    # Save all modified image data using DUAL-WRITE pattern
                    for (
                        img_path,
                        img_data,
                    ) in self.pending_changes.get_modified_images().items():
                        # Extract hash from path
                        media_hash = img_path.stem

                        # 1. Write to filesystem FIRST (source of truth)
                        if self.fs_repo:
                            self.fs_repo.save_media_data(media_hash, img_data)
                            # Also save caption .txt file if caption exists
                            if img_data.caption:
                                self.fs_repo.save_caption_file(
                                    media_hash, img_data.caption
                                )
                        else:
                            # Fallback to old method if repos not initialized
                            if library.library_image_list is not None:
                                library.library_image_list.save_image_data(
                                    img_path, img_data
                                )
                            else:
                                json_path = img_path.with_suffix(".json")
                                img_data.save(json_path)

                        # 2. Then write to database (for fast queries)
                        if self.db_repo:
                            try:
                                self.db_repo.upsert_media(media_hash, img_data)
                            except Exception as e:
                                print(
                                    f"Warning: Database update failed for {media_hash}: {e}"
                                )
                                # Continue anyway - filesystem is the source of truth

            # Handle project changes
            if self.current_project and self.current_project.project_file:
                # Invalidate cache for modified images (they're being written to disk)
                for img_path in self.pending_changes.get_modified_images().keys():
                    if img_path in self._image_data_cache:
                        del self._image_data_cache[img_path]

                # Save all modified image data using DUAL-WRITE pattern
                for (
                    img_path,
                    img_data,
                ) in self.pending_changes.get_modified_images().items():
                    # Extract hash from path
                    media_hash = img_path.stem

                    # 1. Write to filesystem FIRST (source of truth)
                    if self.fs_repo:
                        self.fs_repo.save_media_data(media_hash, img_data)
                        # Also save caption .txt file if caption exists
                        if img_data.caption:
                            self.fs_repo.save_caption_file(media_hash, img_data.caption)
                    else:
                        # Fallback to old method if repos not initialized
                        if self.current_project.image_list is not None:
                            self.current_project.image_list.save_image_data(
                                img_path, img_data
                            )
                        else:
                            json_path = self.current_project.get_image_json_path(
                                img_path
                            )
                            img_data.save(json_path)

                    # 2. Then write to database (for fast queries)
                    if self.db_repo:
                        try:
                            self.db_repo.upsert_media(media_hash, img_data)
                        except Exception as e:
                            print(
                                f"Warning: Database update failed for {media_hash}: {e}"
                            )
                            # Continue anyway - filesystem is the source of truth

                # Save project data
                self.current_project.save()

            # Clear pending changes
            self.pending_changes.clear()

            return True

        except Exception as e:
            print(f"Error saving changes: {e}")
            return False

    def scan_and_add_new_files(self) -> int:
        """
        Scan images directory for new files not in the library/project and add them.
        Creates .json files for new files with filename as name tag.

        Returns:
            Number of new files added
        """
        library = self.get_library()
        if not library or not library.library_dir:
            return 0

        images_dir = library.library_dir / "images"
        if not images_dir.exists():
            return 0

        # Get supported extensions
        config = self.get_config()
        supported_extensions = set(
            config.default_image_extensions + config.default_video_extensions
        )

        # Always update the LIBRARY list, never the PROJECT list automatically
        # Projects should be curated manually.
        current_list = library.library_image_list
        if not current_list:
            return 0

        # Get existing paths in the library
        existing_paths = set(current_list.get_all_paths())

        # Scan for all media files in images directory
        new_files_added = 0
        for file_path in images_dir.iterdir():
            if not file_path.is_file():
                continue

            # Check if it's a supported media file
            if file_path.suffix.lower() not in supported_extensions:
                continue

            # Skip if already in the image list
            if file_path in existing_paths:
                continue

            # Found a new file - create .json if it doesn't exist
            json_path = file_path.with_suffix(".json")
            if not json_path.exists():
                # Create new ImageData with filename as name tag
                from .data_models import ImageData

                media_hash = file_path.stem
                img_data = ImageData(name=media_hash)
                # Add name tag with original filename
                img_data.add_tag("name", file_path.name)
                # Save the JSON
                img_data.save(json_path)

            # Add to the image list
            if current_list.add_image(file_path):
                new_files_added += 1

        # If we added files, save the library/project and emit signals
        if new_files_added > 0:
            # Save the library
            library.save()

            # If in project mode, also save the project
            if self.current_view_mode == "project" and self.current_project:
                self.current_project.save()

            # Rebuild tag list to include tags from new files
            self.rebuild_tag_list()

            # Emit signals to refresh UI
            self.library_changed.emit()
            self.project_changed.emit()

        return new_files_added

    def revert_all_changes(self, force_reload: bool = False) -> bool:
        """
        Discard all pending changes and reload data from disk

        Args:
            force_reload: If True, reload from disk even if there are no pending changes

        Returns:
            True if successfully reverted, False on error
        """
        # If no pending changes and not forcing reload, nothing to do
        if not self.pending_changes.has_changes() and not force_reload:
            return True

        try:
            # Clear pending changes
            self.pending_changes.clear()

            # Clear image data cache to force reload from disk
            self._image_data_cache.clear()

            # Reload library or project from file
            if self.current_view_mode == "library" and self.current_library:
                # Reload library
                library_file = self.current_library.library_file
                if library_file and library_file.exists():
                    self.load_library(library_file)
            elif self.current_view_mode == "project" and self.current_project:
                # Reload project
                project_file = self.current_project.project_file
                if project_file and project_file.exists():
                    # Get library images directory for project reload
                    library = self.get_library()
                    if library:
                        images_dir = library.get_images_directory()
                        from .data_models import ProjectData

                        self.current_project = ProjectData.load(
                            project_file, images_dir
                        )

                        # Rebuild tag list
                        if self.current_project.image_list:
                            self.tag_list.build_from_imagelist(
                                self.current_project.image_list
                            )
                            # Reconnect signal
                            self.current_project.image_list.active_changed.connect(
                                lambda: self.active_image_changed.emit()
                            )
            elif self.project_data and self.project_data.project_file:
                # Legacy project reload
                project_file = self.project_data.project_file
                if project_file and project_file.exists():
                    self.load_project(project_file)

            # Refresh UI
            self.library_changed.emit()
            self.project_changed.emit()
            return True

        except Exception as e:
            print(f"Error reverting changes: {e}")
            return False

    def _move_removed_images_to_deleted_folder(self, removed_images: List[Path]):
        """Move removed images and their associated files to a 'deleted' folder"""
        library = self.get_library()
        if not library or not library.library_dir:
            return

        # Create deleted folder
        deleted_dir = library.library_dir / "deleted"
        deleted_dir.mkdir(exist_ok=True)

        # Move files to deleted folder
        for img_path in removed_images:
            try:
                if img_path.exists():
                    # Move image file
                    new_path = deleted_dir / img_path.name
                    counter = 1
                    while new_path.exists():
                        stem = img_path.stem
                        suffix = img_path.suffix
                        new_path = deleted_dir / f"{stem}_{counter}{suffix}"
                        counter += 1
                    img_path.rename(new_path)

                # Move associated .txt file
                txt_path = img_path.with_suffix(".txt")
                if txt_path.exists():
                    new_txt_path = deleted_dir / txt_path.name
                    counter = 1
                    while new_txt_path.exists():
                        stem = txt_path.stem
                        new_txt_path = deleted_dir / f"{stem}_{counter}.txt"
                        counter += 1
                    txt_path.rename(new_txt_path)

                # Move associated .json file
                json_path = img_path.with_suffix(".json")
                if json_path.exists():
                    new_json_path = deleted_dir / json_path.name
                    counter = 1
                    while new_json_path.exists():
                        stem = json_path.stem
                        new_json_path = deleted_dir / f"{stem}_{counter}.json"
                        counter += 1
                    json_path.rename(new_json_path)

            except Exception as e:
                print(f"Error moving {img_path.name} to deleted folder: {e}")

    def load_image_data(self, image_path: Path) -> ImageData:
        """Load image data (from pending changes if modified, otherwise from cache or disk)"""
        # Check if there's a pending change first (highest priority)
        modified_images = self.pending_changes.get_modified_images()
        if image_path in modified_images:
            return modified_images[image_path]

        # Check cache second
        if image_path in self._image_data_cache:
            return self._image_data_cache[image_path]

        # Load from disk and cache - use current view
        image_list = self.get_image_list()
        if image_list is not None:
            image_data = image_list.get_image_data(image_path)
        else:
            # Fallback to direct load
            json_path = image_path.with_suffix(".json")
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
        # Auto-update caption if there's an active caption profile
        active_profile = None

        # Check for active caption profile in both library and project views
        if self.current_view_mode == "library" and self.current_library:
            # Library view - check if library has active profile
            active_profile = getattr(
                self.current_library, "active_caption_profile", None
            )
        elif self.current_view_mode == "project" and self.current_project:
            # Project view - check project export settings
            active_profile = self.current_project.export.get("active_caption_profile")

        if active_profile:
            try:
                from .utils import parse_export_template, apply_export_template

                template_parts = parse_export_template(active_profile)

                # Get caption profile settings (remove_duplicates, max_tags)
                remove_duplicates = False
                max_tags = None

                if self.current_view_mode == "library" and self.current_library:
                    remove_duplicates = getattr(
                        self.current_library, "caption_profile_remove_duplicates", False
                    )
                    max_tags_val = getattr(
                        self.current_library, "caption_profile_max_tags", 0
                    )
                    max_tags = max_tags_val if max_tags_val > 0 else None
                elif self.current_view_mode == "project" and self.current_project:
                    remove_duplicates = self.current_project.export.get(
                        "caption_profile_remove_duplicates", False
                    )
                    max_tags_val = self.current_project.export.get(
                        "caption_profile_max_tags", 0
                    )
                    max_tags = max_tags_val if max_tags_val > 0 else None

                caption = apply_export_template(
                    template_parts,
                    image_data,
                    remove_duplicates=remove_duplicates,
                    max_tags=max_tags,
                )
                image_data.caption = caption if caption else ""
            except Exception as e:
                # Silently fail if caption generation fails
                print(f"Error auto-generating caption: {e}")

        # Track the change
        self.pending_changes.mark_image_modified(image_path, image_data)

        # Emit signal that image data has changed (for caption updates)
        self.image_data_changed.emit(image_path)

        # Update TagList with any new tags
        for tag in image_data.tags:
            self.tag_list.add_tag(tag.category, tag.value)

    def get_all_tags_in_project(self) -> List[str]:
        """Get all tags for fuzzy search (for backward compatibility)"""
        return self.tag_list.get_all_tags()

    def rebuild_tag_list(self):
        """Rebuild the tag list from all images in the current view (including pending changes)"""
        self.tag_list.clear()
        image_list = self.get_image_list()
        if image_list is not None:
            for img_path in image_list:
                img_data = self.load_image_data(
                    img_path
                )  # Uses pending changes if available
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
        if self.current_project and self.current_project.image_list is not None:
            count = self.current_project.image_list.remove_images(image_paths)

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
        default_dir: Optional[Path] = None,
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
            "project": self.global_config.last_directory_project,
            "import_source": self.global_config.last_directory_import_source,
            "import_dest": self.global_config.last_directory_import_dest,
            "export": self.global_config.last_directory_export,
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
            sidebar_urls = [
                QUrl.fromLocalFile(url)
                for url in self.global_config.file_dialog_sidebar_urls
            ]
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
        if directory_type == "project":
            self.global_config.last_directory_project = str(selected_path)
        elif directory_type == "import_source":
            self.global_config.last_directory_import_source = str(selected_path)
        elif directory_type == "import_dest":
            self.global_config.last_directory_import_dest = str(selected_path)
        elif directory_type == "export":
            self.global_config.last_directory_export = str(selected_path)

        # Save sidebar URLs
        sidebar_urls = dialog.sidebarUrls()
        self.global_config.file_dialog_sidebar_urls = [
            url.toLocalFile() for url in sidebar_urls if url.isLocalFile()
        ]

        self.config_manager.save_config(self.global_config)

        return selected_path

    def get_save_filename(
        self, parent: QWidget, caption: str, default_name: str, file_filter: str
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
            sidebar_urls = [
                QUrl.fromLocalFile(url)
                for url in self.global_config.file_dialog_sidebar_urls
            ]
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
        self.global_config.file_dialog_sidebar_urls = [
            url.toLocalFile() for url in sidebar_urls if url.isLocalFile()
        ]

        self.config_manager.save_config(self.global_config)

        return selected_path

    def get_open_filename(
        self, parent: QWidget, caption: str, file_filter: str
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
            sidebar_urls = [
                QUrl.fromLocalFile(url)
                for url in self.global_config.file_dialog_sidebar_urls
            ]
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
        self.global_config.file_dialog_sidebar_urls = [
            url.toLocalFile() for url in sidebar_urls if url.isLocalFile()
        ]

        self.config_manager.save_config(self.global_config)

        return selected_path
