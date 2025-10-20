"""
Shared data models used across the application
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
from datetime import datetime


@dataclass
class Tag:
    """A single tag with category and value"""
    category: str
    value: str

    def to_dict(self) -> Dict[str, str]:
        return {"category": self.category, "value": self.value}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'Tag':
        return cls(category=data.get("category", ""), value=data.get("value", ""))
    
    def get_value(self) -> str:
        return str(self.value)

    def get_category(self) -> str:
        return str(self.category)

    def __str__(self) -> str:
        return f"{self.category}:{self.value}"

@dataclass
class ImageData:
    """Data for a single image stored in image.json"""
    name: str = ""
    caption: str = ""
    tags: List[Tag] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "caption": self.caption,
            "tags": [tag.to_dict() for tag in self.tags]
        }

    @classmethod
    def load(cls, json_path: Path) -> 'ImageData':
        """Load image data from .json file"""
        if json_path.exists():
            with open(json_path, 'r') as f:
                data = json.load(f)
                tags = [Tag.from_dict(t) for t in data.get("tags", [])]
                return cls(
                    name=data.get("name", ""),
                    caption=data.get("caption", ""),
                    tags=tags
                )
        return cls()

    def save(self, json_path: Path):
        """Save image data to .json file"""
        with open(json_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    def add_tag(self, category: str, value: str):
        """Add a tag to the image"""
        self.tags.append(Tag(category=category, value=value))

    def remove_tag(self, tag: Tag):
        """Remove a tag from the image"""
        if tag in self.tags:
            self.tags.remove(tag)

    def get_tags_by_category(self, category: str) -> List[Tag]:
        """Get all tags of a specific category"""
        return [tag for tag in self.tags if tag.category == category]


@dataclass
class GlobalConfig:
    """Global application configuration (global.json)"""
    hash_length: int = 16
    thumbnail_size: int = 150
    default_import_tag_category: str = "meta"
    default_image_extensions: List[str] = field(default_factory=lambda: [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"])
    recent_projects: List[str] = field(default_factory=list)
    max_recent_projects: int = 10

    # Import dialog settings (remember last used)
    import_source_directory: str = ""
    import_copy_images: bool = False
    import_dest_directory: str = ""
    import_retain_paths: bool = True
    import_caption_enabled: bool = False
    import_caption_category: str = "default"
    import_select_after: bool = True

    # File dialog persistence (remember last directories and pinned shortcuts)
    last_directory_project: str = ""  # For new/open project
    last_directory_import_source: str = ""  # For import source
    last_directory_import_dest: str = ""  # For import destination
    last_directory_export: str = ""  # For export plugins
    file_dialog_sidebar_urls: List[str] = field(default_factory=list)  # Pinned shortcuts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hash_length": self.hash_length,
            "thumbnail_size": self.thumbnail_size,
            "default_import_tag_category": self.default_import_tag_category,
            "default_image_extensions": self.default_image_extensions,
            "recent_projects": self.recent_projects,
            "max_recent_projects": self.max_recent_projects,
            "import_source_directory": self.import_source_directory,
            "import_copy_images": self.import_copy_images,
            "import_dest_directory": self.import_dest_directory,
            "import_retain_paths": self.import_retain_paths,
            "import_caption_enabled": self.import_caption_enabled,
            "import_caption_category": self.import_caption_category,
            "import_select_after": self.import_select_after,
            "last_directory_project": self.last_directory_project,
            "last_directory_import_source": self.last_directory_import_source,
            "last_directory_import_dest": self.last_directory_import_dest,
            "last_directory_export": self.last_directory_export,
            "file_dialog_sidebar_urls": self.file_dialog_sidebar_urls
        }

    def save(self, path: Path):
        """Save configuration to file"""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> 'GlobalConfig':
        """Load configuration from file"""
        if path.exists():
            with open(path, 'r') as f:
                data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
        return cls()


@dataclass
class ProjectData:
    """
    Project-specific data

    Stored in user-selected project.json file
    """
    project_name: str = ""
    description: str = ""
    project_file: Optional[Path] = None  # Path to the project.json file
    image_list: Optional['ImageList'] = None  # The ImageList instance (not serialized directly)
    export: Dict[str, Any] = field(default_factory=dict)  # Export profiles and settings
    filters: Dict[str, Any] = field(default_factory=dict)  # Saved filters
    preferences: Dict[str, Any] = field(default_factory=dict)  # Project-specific preference overrides
    extensions: Dict[str, Any] = field(default_factory=dict)  # Extension data storage

    def get_base_directory(self) -> Optional[Path]:
        """Get the directory containing the project file"""
        if self.project_file:
            return self.project_file.parent
        return None

    def save(self):
        """Save project data to .json file"""
        if self.project_file:
            data = {
                'project_name': self.project_name,
                'description': self.description,
                'images': self.image_list.to_dict() if self.image_list else [],
                'export': self.export,
                'filters': self.filters,
                'preferences': self.preferences,
                'extensions': self.extensions
            }
            with open(self.project_file, 'w') as f:
                json.dump(data, f, indent=2)

            # Mark ImageList as clean after save
            if self.image_list:
                self.image_list.mark_clean()

    @classmethod
    def load(cls, project_file: Path) -> 'ProjectData':
        """
        Load project data from .json file

        Args:
            project_file: Path to .json file
        """
        if project_file.exists():
            with open(project_file, 'r') as f:
                data = json.load(f)
                base_dir = project_file.parent

                # Deserialize ImageList from project data
                images_data = data.get('images', [])
                image_list = ImageList.from_dict(base_dir, images_data)

                return cls(
                    project_name=data.get('project_name', ''),
                    description=data.get('description', ''),
                    project_file=project_file,
                    image_list=image_list,
                    export=data.get('export', {}),
                    filters=data.get('filters', {}),
                    preferences=data.get('preferences', {}),
                    extensions=data.get('extensions', {})
                )

        # New project - create empty ImageList
        base_dir = project_file.parent if project_file else Path.cwd()
        return cls(
            project_file=project_file,
            image_list=ImageList(base_dir)
        )

    def get_all_absolute_image_paths(self) -> List[Path]:
        """Get all images as absolute paths"""
        if self.image_list:
            return self.image_list.get_all_paths()
        return []

    def get_image_json_path(self, image_path: Path) -> Path:
        """Get the .json path for an image"""
        return image_path.with_suffix('.json')

    def set_extension_data(self, extension_name: str, data: Any):
        """Store extension-specific data"""
        self.extensions[extension_name] = data

    def get_extension_data(self, extension_name: str, default: Any = None) -> Any:
        """Retrieve extension-specific data"""
        return self.extensions.get(extension_name, default)


class TagList:
    """Manages all tags in project with fast lookups and incremental updates"""

    def __init__(self):
        self._tags: set = set()  # Full tags "category:value"
        self._categories: set = set()  # Just categories "category:"
        self._sorted_tags: List[str] = []  # Pre-sorted for fuzzy search
        self._sorted_categories: List[str] = []  # Pre-sorted categories

    def add_tag(self, category: str, value: str):
        """Add a tag and update sorted lists"""
        tag_str = f"{category}:{value}"
        cat_str = f"{category}:"

        # Add to sets
        tags_changed = tag_str not in self._tags
        cats_changed = cat_str not in self._categories

        self._tags.add(tag_str)
        self._categories.add(cat_str)

        # Rebuild sorted lists if needed
        if tags_changed or cats_changed:
            self._rebuild_sorted_lists()

    def remove_tag(self, category: str, value: str):
        """Remove a tag and update sorted lists"""
        tag_str = f"{category}:{value}"

        if tag_str in self._tags:
            self._tags.discard(tag_str)
            self._rebuild_sorted_lists()

    def has_tag(self, category: str, value: str) -> bool:
        """Check if tag exists"""
        return f"{category}:{value}" in self._tags

    def get_all_tags(self) -> List[str]:
        """Get all tags sorted (categories first, then full tags)"""
        return self._sorted_categories + self._sorted_tags

    def get_all_categories(self) -> List[str]:
        """Get all categories sorted"""
        return self._sorted_categories.copy()

    def get_all_full_tags(self) -> List[str]:
        """Get all full tags (category:value) sorted"""
        return self._sorted_tags.copy()

    def clear(self):
        """Clear all tags"""
        self._tags.clear()
        self._categories.clear()
        self._sorted_tags.clear()
        self._sorted_categories.clear()

    def build_from_imagelist(self, image_list: 'ImageList'):
        """Build tag list by scanning all images in the ImageList"""
        self.clear()
        for img_path in image_list:
            img_data = image_list.get_image_data(img_path)
            for tag in img_data.tags:
                self.add_tag(tag.category, tag.value)

    def _rebuild_sorted_lists(self):
        """Rebuild sorted lists from sets"""
        self._sorted_categories = sorted(list(self._categories))
        self._sorted_tags = sorted(list(self._tags))


class ImageList:
    """Manages collection of images with their data and selection state"""

    def __init__(self, base_dir: Path):
        self._base_dir: Path = base_dir
        self._image_paths: List[Path] = []  # Absolute paths
        self._image_repeats: Dict[Path, int] = {}  # Repeat count for each image (for dataset balancing)
        self._dirty: bool = False  # Track if changes need to be saved

        # Selection state
        self._selected_images: List[Path] = []  # Images with checkboxes selected
        self._active_image: Optional[Path] = None  # Currently focused image

    def add_image(self, image_path: Path) -> bool:
        """Add image to list if not already present"""
        if image_path not in self._image_paths:
            self._image_paths.append(image_path)
            self._image_repeats[image_path] = 1  # Initialize repeat count to 1
            self._dirty = True
            return True
        return False

    def remove_image(self, image_path: Path) -> bool:
        """Remove image from list"""
        if image_path in self._image_paths:
            self._image_paths.remove(image_path)
            # Clean up repeat data
            if image_path in self._image_repeats:
                del self._image_repeats[image_path]
            self._dirty = True
            return True
        return False

    def remove_images(self, image_paths: List[Path]) -> int:
        """
        Remove multiple images from the list

        Args:
            image_paths: List of image paths to remove

        Returns:
            Number of images successfully removed
        """
        count = 0
        for img_path in image_paths:
            if self.remove_image(img_path):
                count += 1
                # Update selection state
                if img_path in self._selected_images:
                    self._selected_images.remove(img_path)
                if self._active_image == img_path:
                    self._active_image = None
        return count

    def remove_selected(self) -> int:
        """
        Remove all selected images from the list

        Returns:
            Number of images removed
        """
        if not self._selected_images:
            return 0

        selected_copy = self._selected_images.copy()
        count = self.remove_images(selected_copy)
        self._selected_images.clear()
        return count

    # Selection methods
    def select(self, image_path: Path):
        """Select an image"""
        if image_path in self._image_paths and image_path not in self._selected_images:
            self._selected_images.append(image_path)

    def deselect(self, image_path: Path):
        """Deselect an image"""
        if image_path in self._selected_images:
            self._selected_images.remove(image_path)

    def toggle_selection(self, image_path: Path):
        """Toggle selection of an image"""
        if image_path in self._selected_images:
            self._selected_images.remove(image_path)
        elif image_path in self._image_paths:
            self._selected_images.append(image_path)

    def select_all(self):
        """Select all images"""
        self._selected_images = self._image_paths.copy()

    def clear_selection(self):
        """Clear all selected images"""
        self._selected_images.clear()

    def get_selected(self) -> List[Path]:
        """Get list of selected images"""
        return self._selected_images.copy()

    def set_active(self, image_path: Path):
        """Set the active (focused) image"""
        if image_path in self._image_paths:
            self._active_image = image_path

    def get_active(self) -> Optional[Path]:
        """Get the active image"""
        return self._active_image

    def get_working_images(self) -> List[Path]:
        """Get images to work on: selected images if any, otherwise active image"""
        if self._selected_images:
            return self._selected_images.copy()
        elif self._active_image:
            return [self._active_image]
        return []

    def get_all_paths(self) -> List[Path]:
        """Get all image paths"""
        return self._image_paths.copy()

    def get_image_data(self, image_path: Path) -> ImageData:
        """Load image data from JSON file"""
        json_path = self._get_json_path(image_path)
        return ImageData.load(json_path)

    def save_image_data(self, image_path: Path, image_data: ImageData):
        """Save image data to JSON file"""
        json_path = self._get_json_path(image_path)
        image_data.save(json_path)

    def set_repeat(self, image_path: Path, repeat_count: int):
        """Set the repeat count for an image (for dataset balancing)"""
        if image_path in self._image_paths:
            self._image_repeats[image_path] = max(1, repeat_count)  # Ensure minimum of 1
            self._dirty = True

    def get_repeat(self, image_path: Path) -> int:
        """Get the repeat count for an image (defaults to 1)"""
        return self._image_repeats.get(image_path, 1)

    def get_all_repeats(self) -> Dict[Path, int]:
        """Get all repeat counts as a dictionary"""
        return self._image_repeats.copy()

    def to_dict(self) -> List[Dict[str, Any]]:
        """Serialize to project.json format"""
        return [{
            "path": str(img_path.relative_to(self._base_dir)),
            "repeats": self._image_repeats.get(img_path, 1)
        } for img_path in self._image_paths]

    @classmethod
    def from_dict(cls, base_dir: Path, data: List[Dict[str, Any]]) -> 'ImageList':
        """Deserialize from project.json"""
        image_list = cls(base_dir)
        for img_dict in data:
            rel_path = img_dict.get("path", "")
            if rel_path:
                img_path = base_dir / rel_path
                image_list.add_image(img_path)
                # Load repeat count (defaults to 1 if not present for backward compatibility)
                repeats = img_dict.get("repeats", 1)
                image_list._image_repeats[img_path] = repeats
        # Clear dirty flag after loading
        image_list._dirty = False
        return image_list

    @classmethod
    def create_filtered(cls, base_dir: Path, image_paths: List[Path]) -> 'ImageList':
        """Create a new ImageList with a subset of image paths (for filtered views)"""
        image_list = cls(base_dir)
        for img_path in image_paths:
            image_list.add_image(img_path)
        # Clear dirty flag - filtered list is a view, not a modification
        image_list._dirty = False
        return image_list

    def is_dirty(self) -> bool:
        """Check if there are unsaved changes"""
        return self._dirty

    def mark_clean(self):
        """Mark as saved (clear dirty flag)"""
        self._dirty = False

    def _get_json_path(self, image_path: Path) -> Path:
        """Get the .json path for an image"""
        return image_path.with_suffix('.json')

    def __len__(self) -> int:
        """Return number of images"""
        return len(self._image_paths)

    def __iter__(self):
        """Allow iteration over image paths"""
        return iter(self._image_paths)


class PendingChanges:
    """Tracks all pending changes before they are saved to disk"""

    def __init__(self):
        self._modified_images: Dict[Path, ImageData] = {}  # image_path -> modified ImageData
        self._project_modified: bool = False

    def mark_image_modified(self, image_path: Path, image_data: ImageData):
        """Mark an image's data as modified"""
        self._modified_images[image_path] = image_data

    def mark_project_modified(self):
        """Mark project data as modified"""
        self._project_modified = True

    def has_changes(self) -> bool:
        """Check if there are any pending changes"""
        return bool(self._modified_images) or self._project_modified

    def get_modified_images(self) -> Dict[Path, ImageData]:
        """Get all modified image data"""
        return self._modified_images.copy()

    def get_summary(self) -> str:
        """Generate a human-readable summary of changes"""
        lines = []

        if self._project_modified:
            lines.append("• Project structure modified")

        if self._modified_images:
            lines.append(f"• {len(self._modified_images)} image(s) modified:")
            for img_path in sorted(self._modified_images.keys())[:10]:  # Show max 10
                lines.append(f"  - {img_path.name}")
            if len(self._modified_images) > 10:
                lines.append(f"  ... and {len(self._modified_images) - 10} more")

        return "\n".join(lines) if lines else "No changes"

    def clear(self):
        """Clear all pending changes"""
        self._modified_images.clear()
        self._project_modified = False

    def get_change_count(self) -> int:
        """Get total number of changes"""
        count = 0
        if self._project_modified:
            count += 1
        count += len(self._modified_images)
        return count


