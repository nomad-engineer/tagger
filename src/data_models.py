"""
Shared data models used across the application
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal


@dataclass
class Tag:
    """A single tag with category and value"""

    category: str
    value: str

    def to_dict(self) -> Dict[str, str]:
        return {"category": self.category, "value": self.value}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Tag":
        return cls(category=data.get("category", ""), value=data.get("value", ""))

    def get_value(self) -> str:
        return str(self.value)

    def get_category(self) -> str:
        return str(self.category)

    def __str__(self) -> str:
        return f"{self.category}:{self.value}"


@dataclass
class MediaData:
    """
    Base class for all media types (images, masks, video frames)

    This provides common fields and methods for all media types.
    Files are stored as: hash.ext, hash.json, hash.txt
    """

    type: str = "image"  # "image", "mask", "video_frame"
    name: str = ""
    caption: str = ""
    tags: List[Tag] = field(default_factory=list)
    related: Dict[str, List[str]] = field(
        default_factory=dict
    )  # Dict of relationship_type -> [list of media hashes]
    metadata: Dict[str, Any] = field(
        default_factory=dict
    )  # Additional metadata (dimensions, created date, etc.)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "type": self.type,
            "name": self.name,
            "caption": self.caption,
            "tags": [tag.to_dict() for tag in self.tags],
            "related": self.related,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaData":
        """Create MediaData from dictionary - routes to correct subclass based on type"""
        media_type = data.get("type", "image")

        if media_type == "mask":
            return MaskData.from_dict_impl(data)
        elif media_type == "video_frame":
            return VideoFrameData.from_dict_impl(data)
        elif media_type == "crop":
            return CropData.from_dict_impl(data)
        else:
            # Default to ImageData for backward compatibility
            return ImageData.from_dict_impl(data)

    @classmethod
    def from_dict_impl(cls, data: Dict[str, Any]) -> "MediaData":
        """Implementation of from_dict for this specific class"""
        tags = [Tag.from_dict(t) for t in data.get("tags", [])]
        related = data.get("related", {})
        metadata = data.get("metadata", {})

        return cls(
            type=data.get("type", "image"),
            name=data.get("name", ""),
            caption=data.get("caption", ""),
            tags=tags,
            related=related,
            metadata=metadata,
        )

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

    def add_related(self, relationship_type: str, image_path: str):
        """Add a related image path for a given relationship type"""
        if relationship_type not in self.related:
            self.related[relationship_type] = []
        if image_path not in self.related[relationship_type]:
            self.related[relationship_type].append(image_path)

    def remove_related(self, relationship_type: str, image_path: str):
        """Remove a related image path for a given relationship type"""
        if (
            relationship_type in self.related
            and image_path in self.related[relationship_type]
        ):
            self.related[relationship_type].remove(image_path)
            # Remove empty relationship type
            if not self.related[relationship_type]:
                del self.related[relationship_type]

    def get_related(self, relationship_type: str) -> List[str]:
        """Get all related image paths for a given relationship type"""
        return self.related.get(relationship_type, [])

    def has_related(self, relationship_type: str) -> bool:
        """Check if image has any related images of a given type"""
        return (
            relationship_type in self.related
            and len(self.related[relationship_type]) > 0
        )

    def get_display_name(self) -> str:
        """
        Get display name for the image

        Checks for name:{filename} tag first, falls back to self.name field
        This allows flexibility to rename images via tag editing and supports
        future AI-generated filenames

        Returns:
            Display name string
        """
        # Check for name:* tag
        name_tags = self.get_tags_by_category("name")
        if name_tags:
            # Return the first name tag value
            return name_tags[0].value

        # Fallback to name field (usually the hash)
        return self.name if self.name else "Unnamed"


@dataclass
class ImageData(MediaData):
    """Data for a single image stored in image.json"""

    type: str = "image"  # Override default

    # Keep backward compatibility - don't require metadata in constructor
    def __post_init__(self):
        """Ensure metadata dict exists"""
        if not hasattr(self, "metadata") or self.metadata is None:
            object.__setattr__(self, "metadata", {})

    @classmethod
    def from_dict_impl(cls, data: Dict[str, Any]) -> "ImageData":
        """Implementation of from_dict for ImageData"""
        tags = [Tag.from_dict(t) for t in data.get("tags", [])]
        related = data.get("related", {})
        metadata = data.get("metadata", {})

        # Backward compatibility: convert old similar_images to related["similar"]
        if "similar_images" in data and not related.get("similar"):
            similar_raw = data.get("similar_images", [])
            # Convert old format [(filename, distance), ...] to just filenames
            similar_paths = [item[0] for item in similar_raw] if similar_raw else []
            if not related:
                related = {}
            related["similar"] = similar_paths

        return cls(
            type="image",
            name=data.get("name", ""),
            caption=data.get("caption", ""),
            tags=tags,
            related=related,
            metadata=metadata,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Override to maintain backward compatibility - don't include type/metadata if empty"""
        result = {
            "name": self.name,
            "caption": self.caption,
            "tags": [tag.to_dict() for tag in self.tags],
            "related": self.related,
        }
        # Only include metadata if it has content
        if self.metadata:
            result["metadata"] = self.metadata
        # Only include type if it's not the default "image" (for backward compatibility)
        if self.type != "image":
            result["type"] = self.type
        return result

    @classmethod
    def load(cls, json_path: Path) -> "ImageData":
        """Load image data from .json file"""
        if json_path.exists():
            with open(json_path, "r") as f:
                data = json.load(f)
                tags = [Tag.from_dict(t) for t in data.get("tags", [])]

                # Load new related structure
                related = data.get("related", {})

                # Backward compatibility: convert old similar_images to related["similar"]
                if "similar_images" in data and not related:
                    similar_raw = data.get("similar_images", [])
                    # Convert old format [(filename, distance), ...] to just filenames
                    similar_paths = (
                        [item[0] for item in similar_raw] if similar_raw else []
                    )
                    related = {"similar": similar_paths}

                return cls(
                    name=data.get("name", ""),
                    caption=data.get("caption", ""),
                    tags=tags,
                    related=related,
                )
        return cls()

    def save(self, json_path: Path):
        """Save image data to .json file"""
        with open(json_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


@dataclass
class MaskData(MediaData):
    """
    Data for a mask/segmentation image

    Masks are first-class media items that reference a source image.
    Stored just like images: hash.png, hash.json, hash.txt
    """

    type: str = "mask"
    source_image: str = ""  # Hash of the parent image this mask belongs to
    mask_category: str = ""  # What this masks (e.g., "person", "background", "object")

    def __post_init__(self):
        """Ensure metadata dict exists"""
        if not hasattr(self, "metadata") or self.metadata is None:
            object.__setattr__(self, "metadata", {})

    @classmethod
    def from_dict_impl(cls, data: Dict[str, Any]) -> "MaskData":
        """Implementation of from_dict for MaskData"""
        tags = [Tag.from_dict(t) for t in data.get("tags", [])]
        related = data.get("related", {})
        metadata = data.get("metadata", {})

        return cls(
            type="mask",
            name=data.get("name", ""),
            caption=data.get("caption", ""),
            tags=tags,
            related=related,
            metadata=metadata,
            source_image=data.get("source_image", ""),
            mask_category=data.get("mask_category", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Override to include mask-specific fields"""
        result = {
            "type": "mask",
            "source_image": self.source_image,
            "mask_category": self.mask_category,
            "name": self.name,
            "caption": self.caption,
            "tags": [tag.to_dict() for tag in self.tags],
            "related": self.related,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    def load(self, json_path: Path) -> "MaskData":
        """Load mask data from .json file"""
        if json_path.exists():
            with open(json_path, "r") as f:
                data = json.load(f)
                return self.from_dict_impl(data)
        return MaskData()

    def save(self, json_path: Path):
        """Save mask data to .json file"""
        with open(json_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


@dataclass
class VideoFrameData(MediaData):
    """
    Data for a video frame extracted from a video

    Each frame is treated as an image with additional video metadata.
    Stored like images: hash.png, hash.json, hash.txt
    """

    type: str = "video_frame"
    source_video: str = ""  # Hash of the source video file
    frame_index: int = 0  # Frame number in the video
    timestamp: float = 0.0  # Timestamp in seconds

    def __post_init__(self):
        """Ensure metadata dict exists"""
        if not hasattr(self, "metadata") or self.metadata is None:
            object.__setattr__(self, "metadata", {})

    @classmethod
    def from_dict_impl(cls, data: Dict[str, Any]) -> "VideoFrameData":
        """Implementation of from_dict for VideoFrameData"""
        tags = [Tag.from_dict(t) for t in data.get("tags", [])]
        related = data.get("related", {})
        metadata = data.get("metadata", {})

        return cls(
            type="video_frame",
            name=data.get("name", ""),
            caption=data.get("caption", ""),
            tags=tags,
            related=related,
            metadata=metadata,
            source_video=data.get("source_video", ""),
            frame_index=data.get("frame_index", 0),
            timestamp=data.get("timestamp", 0.0),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Override to include video frame-specific fields"""
        result = {
            "type": "video_frame",
            "source_video": self.source_video,
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "name": self.name,
            "caption": self.caption,
            "tags": [tag.to_dict() for tag in self.tags],
            "related": self.related,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    def load(self, json_path: Path) -> "VideoFrameData":
        """Load video frame data from .json file"""
        if json_path.exists():
            with open(json_path, "r") as f:
                data = json.load(f)
                return self.from_dict_impl(data)
        return VideoFrameData()

    def save(self, json_path: Path):
        """Save video frame data to .json file"""
        with open(json_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


@dataclass
class CropData(MediaData):
    """
    Data for a cropped image derived from a parent image

    Cropped views are first-class media items that reference a source image
    and store crop coordinates for recreation. Stored like images: hash.png, hash.json, hash.txt
    """

    type: str = "crop"
    parent_image: str = ""  # Hash of the parent image this crop belongs to
    crop_rect: Tuple[int, int, int, int] = (
        0,
        0,
        0,
        0,
    )  # (x, y, width, height) in parent image coordinates
    aspect_ratio: str = "auto"  # Aspect ratio used: "auto" or "width:height"
    created_at: str = ""  # ISO timestamp of creation

    def __post_init__(self):
        """Ensure metadata dict exists"""
        if not hasattr(self, "metadata") or self.metadata is None:
            object.__setattr__(self, "metadata", {})

    @classmethod
    def from_dict_impl(cls, data: Dict[str, Any]) -> "CropData":
        """Implementation of from_dict for CropData"""
        tags = [Tag.from_dict(t) for t in data.get("tags", [])]
        related = data.get("related", {})
        metadata = data.get("metadata", {})

        # Handle crop_rect as list or tuple
        crop_rect = data.get("crop_rect", (0, 0, 0, 0))
        if isinstance(crop_rect, list):
            crop_rect = tuple(crop_rect)

        return cls(
            type="crop",
            name=data.get("name", ""),
            caption=data.get("caption", ""),
            tags=tags,
            related=related,
            metadata=metadata,
            parent_image=data.get("parent_image", ""),
            crop_rect=crop_rect,
            aspect_ratio=data.get("aspect_ratio", "auto"),
            created_at=data.get("created_at", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Override to include crop-specific fields"""
        result = {
            "type": "crop",
            "parent_image": self.parent_image,
            "crop_rect": list(self.crop_rect),  # Convert tuple to list for JSON
            "aspect_ratio": self.aspect_ratio,
            "created_at": self.created_at,
            "name": self.name,
            "caption": self.caption,
            "tags": [tag.to_dict() for tag in self.tags],
            "related": self.related,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    def load(self, json_path: Path) -> "CropData":
        """Load crop data from .json file"""
        if json_path.exists():
            with open(json_path, "r") as f:
                data = json.load(f)
                return self.from_dict_impl(data)
        return CropData()

    def save(self, json_path: Path):
        """Save crop data to .json file"""
        with open(json_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def get_crop_area(self) -> Tuple[int, int, int, int]:
        """Get crop rectangle as (x, y, width, height)"""
        return self.crop_rect

    def set_crop_area(self, x: int, y: int, width: int, height: int):
        """Set crop rectangle coordinates"""
        self.crop_rect = (x, y, width, height)


@dataclass
class GlobalConfig:
    """Global application configuration (global.json)"""

    hash_length: int = 16
    thumbnail_size: int = 150
    default_import_tag_category: str = "meta"
    default_image_extensions: List[str] = field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"]
    )
    default_video_extensions: List[str] = field(
        default_factory=lambda: [
            ".mp4",
            ".avi",
            ".mov",
            ".mkv",
            ".webm",
            ".flv",
            ".wmv",
            ".m4v",
        ]
    )
    recent_projects: List[str] = field(
        default_factory=list
    )  # Deprecated - use recent_libraries
    max_recent_projects: int = 10  # Deprecated - use max_recent_libraries
    recent_libraries: List[str] = field(default_factory=list)
    max_recent_libraries: int = 10

    # Video settings
    video_autoplay: bool = False

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
    file_dialog_sidebar_urls: List[str] = field(
        default_factory=list
    )  # Pinned shortcuts

    # Crop/mask tool settings
    custom_resolution_list: List[str] = field(
        default_factory=list
    )  # Format: ["128x128", "256x256", "512x512"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hash_length": self.hash_length,
            "thumbnail_size": self.thumbnail_size,
            "default_import_tag_category": self.default_import_tag_category,
            "default_image_extensions": self.default_image_extensions,
            "recent_projects": self.recent_projects,
            "max_recent_projects": self.max_recent_projects,
            "recent_libraries": self.recent_libraries,
            "max_recent_libraries": self.max_recent_libraries,
            "video_autoplay": self.video_autoplay,
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
            "file_dialog_sidebar_urls": self.file_dialog_sidebar_urls,
            "custom_resolution_list": self.custom_resolution_list,
        }

    def save(self, path: Path):
        """Save configuration to file"""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "GlobalConfig":
        """Load configuration from file"""
        if path.exists():
            with open(path, "r") as f:
                data = json.load(f)
                return cls(
                    **{k: v for k, v in data.items() if k in cls.__annotations__}
                )
        return cls()


@dataclass
class ProjectData:
    """
    Project-specific data

    Projects now live within a library and reference images from the library's image list.
    Stored in projects/<project_name>.json within the library directory.
    """

    project_name: str = ""
    description: str = ""
    project_file: Optional[Path] = None  # Path to the project.json file
    library_ref: Optional[Path] = (
        None  # Reference to parent library.json (for finding library)
    )
    image_list: Optional["ImageList"] = (
        None  # The ImageList instance (not serialized directly)
    )
    export: Dict[str, Any] = field(default_factory=dict)  # Export profiles and settings
    filters: Dict[str, Any] = field(default_factory=dict)  # Saved filters
    preferences: Dict[str, Any] = field(
        default_factory=dict
    )  # Project-specific preference overrides
    extensions: Dict[str, Any] = field(default_factory=dict)  # Extension data storage

    def get_base_directory(self) -> Optional[Path]:
        """
        Get the directory containing the project file (deprecated)

        Note: In the new library architecture, projects reference images from the library,
        not from the project directory. Use library.get_images_directory() instead.
        """
        if self.project_file:
            return self.project_file.parent
        return None

    def save(self):
        """Save project data to .json file"""
        if self.project_file:
            data = {
                "project_name": self.project_name,
                "description": self.description,
                "library_ref": str(self.library_ref) if self.library_ref else None,
                "images": self.image_list.to_dict() if self.image_list else [],
                "export": self.export,
                "filters": self.filters,
                "preferences": self.preferences,
                "extensions": self.extensions,
            }
            with open(self.project_file, "w") as f:
                json.dump(data, f, indent=2)

            # Mark ImageList as clean after save
            if self.image_list:
                self.image_list.mark_clean()

    @classmethod
    def load(
        cls, project_file: Path, library_images_dir: Optional[Path] = None
    ) -> "ProjectData":
        """
        Load project data from .json file

        Args:
            project_file: Path to .json file
            library_images_dir: Images directory from library (for ImageList base_dir)
        """
        if project_file.exists():
            with open(project_file, "r") as f:
                data = json.load(f)

                # Determine base directory for ImageList
                # In new architecture, use library's images directory
                # In old architecture (backward compat), use project directory
                if library_images_dir:
                    base_dir = library_images_dir
                else:
                    # Backward compatibility
                    base_dir = project_file.parent

                # Deserialize ImageList from project data
                images_data = data.get("images", [])
                image_list = ImageList.from_dict(base_dir, images_data)

                # Get library reference
                library_ref_str = data.get("library_ref")
                library_ref = Path(library_ref_str) if library_ref_str else None

                return cls(
                    project_name=data.get("project_name", ""),
                    description=data.get("description", ""),
                    project_file=project_file,
                    library_ref=library_ref,
                    image_list=image_list,
                    export=data.get("export", {}),
                    filters=data.get("filters", {}),
                    preferences=data.get("preferences", {}),
                    extensions=data.get("extensions", {}),
                )

        # New project - create empty ImageList
        base_dir = (
            library_images_dir
            if library_images_dir
            else (project_file.parent if project_file else Path.cwd())
        )
        return cls(project_file=project_file, image_list=ImageList(base_dir))

    def get_all_absolute_image_paths(self) -> List[Path]:
        """Get all images as absolute paths"""
        if self.image_list:
            return self.image_list.get_all_paths()
        return []

    def get_image_json_path(self, image_path: Path) -> Path:
        """Get the .json path for an image"""
        return image_path.with_suffix(".json")

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

    def build_from_imagelist(self, image_list: "ImageList"):
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


class ImageList(QObject):
    """Manages collection of images with their data and selection state"""

    # Signal emitted when active image changes
    active_changed = pyqtSignal(object)  # Emits Path when active changes

    def __init__(self, base_dir: Path):
        super().__init__()
        self._base_dir: Path = base_dir
        self._image_paths: List[Path] = []  # Absolute paths
        self._image_repeats: Dict[
            Path, int
        ] = {}  # Repeat count for each image (for dataset balancing)
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

    def update_image_path(self, old_path: Path, new_path: Path) -> bool:
        """
        Update image path when image is moved

        Args:
            old_path: Current path of the image
            new_path: New path of the image

        Returns:
            True if path was updated, False if old_path not found
        """
        if old_path not in self._image_paths:
            return False

        # Update path in image list
        idx = self._image_paths.index(old_path)
        self._image_paths[idx] = new_path

        # Update repeat data
        if old_path in self._image_repeats:
            repeat_count = self._image_repeats[old_path]
            del self._image_repeats[old_path]
            self._image_repeats[new_path] = repeat_count

        # Update selection state
        if old_path in self._selected_images:
            idx = self._selected_images.index(old_path)
            self._selected_images[idx] = new_path

        # Update active image
        if self._active_image == old_path:
            self._active_image = new_path

        self._dirty = True
        return True

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
            self.active_changed.emit(image_path)

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
            self._image_repeats[image_path] = (
                repeat_count  # Allow any value including 0
            )
            self._dirty = True

    def set_order(self, ordered_paths: List[Path]) -> bool:
        """Reorder images according to the provided order"""
        if not ordered_paths:
            return False

        # Create a set for fast lookup
        original_set = set(self._image_paths)
        ordered_set = set(ordered_paths)

        # Ensure all ordered paths exist in original list
        if not ordered_set.issubset(original_set):
            return False

        # Filter ordered_paths to only include paths that exist in this image list
        valid_ordered_paths = [path for path in ordered_paths if path in original_set]

        # Update the image paths order
        self._image_paths = valid_ordered_paths
        self._dirty = True
        return True

    def get_repeat(self, image_path: Path) -> int:
        """Get the repeat count for an image (defaults to 1)"""
        return self._image_repeats.get(image_path, 1)

    def get_all_repeats(self) -> Dict[Path, int]:
        """Get all repeat counts as a dictionary"""
        return self._image_repeats.copy()

    def to_dict(self) -> List[Dict[str, Any]]:
        """Serialize to project.json format"""
        return [
            {
                "path": str(img_path.relative_to(self._base_dir)),
                "repeats": self._image_repeats.get(img_path, 1),
            }
            for img_path in self._image_paths
        ]

    @classmethod
    def from_dict(cls, base_dir: Path, data) -> "ImageList":
        """Deserialize from project.json"""
        image_list = cls(base_dir)

        # Handle case where data might not be a list of dicts
        if not isinstance(data, list):
            return image_list

        for img_dict in data:
            if not isinstance(img_dict, dict):
                continue

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
    def create_filtered(cls, base_dir: Path, image_paths: List[Path]) -> "ImageList":
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
        return image_path.with_suffix(".json")

    def copy_image_from(self, source_image_list: "ImageList", image_path: Path) -> bool:
        """
        Copy an image and its data from another ImageList to this one

        Args:
            source_image_list: The source ImageList to copy from
            image_path: The image path in the source list

        Returns:
            True if image was added, False if already present
        """
        # Add image to this list
        if not self.add_image(image_path):
            return False  # Already exists

        # Copy image data
        source_data = source_image_list.get_image_data(image_path)
        self.save_image_data(image_path, source_data)

        # Copy repeat count
        repeat_count = source_image_list.get_repeat(image_path)
        self.set_repeat(image_path, repeat_count)

        return True

    def copy_images_from(
        self, source_image_list: "ImageList", image_paths: List[Path]
    ) -> int:
        """
        Copy multiple images and their data from another ImageList

        Args:
            source_image_list: The source ImageList to copy from
            image_paths: List of image paths to copy

        Returns:
            Number of images successfully copied
        """
        count = 0
        for img_path in image_paths:
            if self.copy_image_from(source_image_list, img_path):
                count += 1
        return count

    def __len__(self) -> int:
        """Return number of images"""
        return len(self._image_paths)

    def __iter__(self):
        """Allow iteration over image paths"""
        return iter(self._image_paths)


class PendingChanges:
    """Tracks all pending changes before they are saved to disk"""

    def __init__(self):
        self._modified_images: Dict[
            Path, ImageData
        ] = {}  # image_path -> modified ImageData
        self._project_modified: bool = False
        self._library_modified: bool = False
        self._removed_images: List[Path] = []  # Track images removed from library

    def mark_image_modified(self, image_path: Path, image_data: ImageData):
        """Mark an image's data as modified"""
        self._modified_images[image_path] = image_data

    def mark_project_modified(self):
        """Mark project data as modified"""
        self._project_modified = True

    def mark_library_modified(self):
        """Mark library structure as modified"""
        self._library_modified = True

    def mark_image_removed(self, image_path: Path):
        """Mark an image as removed from library"""
        if image_path not in self._removed_images:
            self._removed_images.append(image_path)

    def has_changes(self) -> bool:
        """Check if there are any pending changes"""
        return (
            bool(self._modified_images)
            or self._project_modified
            or self._library_modified
            or len(self._removed_images) > 0
        )

    def get_modified_images(self) -> Dict[Path, ImageData]:
        """Get all modified image data"""
        return self._modified_images.copy()

    def get_removed_images(self) -> List[Path]:
        """Get all removed images"""
        return self._removed_images.copy()

    def get_summary(self) -> str:
        """Generate a human-readable summary of changes"""
        lines = []

        if self._project_modified:
            lines.append("• Project structure modified")

        if self._library_modified:
            lines.append("• Library structure modified")

        if self._removed_images:
            lines.append(f"• {len(self._removed_images)} image(s) removed:")
            for img_path in sorted(self._removed_images)[:10]:  # Show max 10
                lines.append(f"  - {img_path.name}")
            if len(self._removed_images) > 10:
                lines.append(f"  ... and {len(self._removed_images) - 10} more")

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
        self._library_modified = False
        self._removed_images.clear()

    def get_change_count(self) -> int:
        """Get total number of changes"""
        count = 0
        if self._project_modified:
            count += 1
        if self._library_modified:
            count += 1
        count += len(self._removed_images)
        count += len(self._modified_images)
        return count


@dataclass
class ImageLibrary:
    """
    Image Library data - contains all images and projects

    The library enforces a flat file structure for images with perceptual hash-based
    filenames to avoid duplicates and detect identical images.

    Stored in library.json at the library root directory
    """

    library_name: str = ""
    library_dir: Optional[Path] = None  # Absolute path to library directory
    library_file: Optional[Path] = None  # Path to library.json file
    library_image_list: Optional[ImageList] = None  # All images in library
    projects: Dict[str, str] = field(
        default_factory=dict
    )  # project_name -> project_file_path (relative to library)
    similar_images: Dict[str, List[str]] = field(
        default_factory=dict
    )  # image_hash -> [similar_image_hashes]
    metadata: Dict[str, Any] = field(
        default_factory=dict
    )  # Additional library metadata
    filters: Dict[str, Any] = field(
        default_factory=dict
    )  # Saved filters for library view
    # Caption profile fields
    active_caption_profile: str = ""  # Currently active caption profile
    caption_profiles: List[str] = field(default_factory=list)  # Saved caption profiles

    def get_library_directory(self) -> Optional[Path]:
        """Get the library directory"""
        return self.library_dir

    def get_images_directory(self) -> Optional[Path]:
        """Get the images directory within the library (flat structure)"""
        if self.library_dir:
            return self.library_dir / "images"
        return None

    def get_projects_directory(self) -> Optional[Path]:
        """Get the projects directory within the library"""
        if self.library_dir:
            return self.library_dir / "projects"
        return None

    def add_project(self, project_name: str, project_file: Path):
        """Add a project to the library"""
        if self.library_dir:
            rel_path = project_file.relative_to(self.library_dir)
            self.projects[project_name] = str(rel_path)

    def remove_project(self, project_name: str) -> bool:
        """Remove a project from the library"""
        if project_name in self.projects:
            del self.projects[project_name]
            return True
        return False

    def get_project_file(self, project_name: str) -> Optional[Path]:
        """Get the absolute path to a project file"""
        if project_name in self.projects and self.library_dir:
            rel_path = self.projects[project_name]
            return self.library_dir / rel_path
        return None

    def list_projects(self) -> List[str]:
        """Get list of all project names"""
        return list(self.projects.keys())

    def add_similar_images(self, image_hash: str, similar_hashes: List[str]):
        """Store similar images for an image"""
        self.similar_images[image_hash] = similar_hashes

    def get_similar_images(self, image_hash: str) -> List[str]:
        """Get similar images for an image hash"""
        return self.similar_images.get(image_hash, [])

    def save(self):
        """Save library data to library.json"""
        if self.library_file and self.library_dir:
            data = {
                "library_name": self.library_name,
                "images": self.library_image_list.to_dict()
                if self.library_image_list
                else [],
                "projects": self.projects,
                "similar_images": self.similar_images,
                "metadata": self.metadata,
                "filters": self.filters,
                "active_caption_profile": self.active_caption_profile,
                "caption_profiles": self.caption_profiles,
            }
            with open(self.library_file, "w") as f:
                json.dump(data, f, indent=2)

            # Mark ImageList as clean after save
            if self.library_image_list:
                self.library_image_list.mark_clean()

    @classmethod
    def load(cls, library_file: Path) -> "ImageLibrary":
        """Load library from library.json file"""
        library_dir = library_file.parent

        try:
            if not library_file.exists():
                print(f"❌ Library file does not exist: {library_file}")
                return cls(
                    library_dir=library_dir,
                    library_file=library_file,
                    library_image_list=ImageList(library_dir / "images"),
                )

            print(f"🔧 Loading library from: {library_file}")
            with open(library_file, "r") as f:
                data = json.load(f)

            print(f"🔧 Library data loaded successfully, type: {type(data)}")
            if isinstance(data, dict):
                print(f"🔧 Library keys: {list(data.keys())}")

            # Deserialize library ImageList with error handling
            images_data = data.get("images", [])
            print(
                f"🔧 Images data type: {type(images_data)}, length: {len(images_data) if isinstance(images_data, list) else 'N/A'}"
            )

            images_dir = library_dir / "images"
            print(f"🔧 Creating ImageList from directory: {images_dir}")

            try:
                library_image_list = ImageList.from_dict(images_dir, images_data)
                print(f"🔧 ImageList created successfully")
            except Exception as e:
                print(f"❌ Error creating ImageList: {e}")
                print(f"🔧 Using empty ImageList as fallback")
                library_image_list = ImageList(images_dir)

            # Create library with error handling for each field
            try:
                library_name = data.get("library_name", "")
                projects = data.get("projects", {})
                similar_images = data.get("similar_images", {})
                metadata = data.get("metadata", {})
                filters = data.get("filters", {})
                active_caption_profile = data.get("active_caption_profile", "")
                caption_profiles = data.get("caption_profiles", [])

                print(f"🔧 Creating ImageLibrary instance...")
                result = cls(
                    library_name=library_name,
                    library_dir=library_dir,
                    library_file=library_file,
                    library_image_list=library_image_list,
                    projects=projects,
                    similar_images=similar_images,
                    metadata=metadata,
                    filters=filters,
                    active_caption_profile=active_caption_profile,
                    caption_profiles=caption_profiles,
                )
                print(f"✅ Library loaded successfully: {library_name}")
                return result

            except Exception as e:
                print(f"❌ Error creating ImageLibrary instance: {e}")
                import traceback

                traceback.print_exc()
                # Return minimal library as fallback
                return cls(
                    library_name="Default Library",
                    library_dir=library_dir,
                    library_file=library_file,
                    library_image_list=library_image_list,
                )

        except Exception as e:
            print(f"❌ Critical error loading library: {e}")
            import traceback

            traceback.print_exc()
            # Return empty library as last resort
            return cls(
                library_dir=library_dir,
                library_file=library_file,
                library_image_list=ImageList(library_dir / "images"),
            )

        # New library - create empty ImageList
        images_dir = library_dir / "images"
        return cls(
            library_file=library_file,
            library_dir=library_dir,
            library_image_list=ImageList(images_dir),
            active_caption_profile="",
            caption_profiles=[],
        )

    @classmethod
    def create_new(cls, library_dir: Path, library_name: str) -> "ImageLibrary":
        """Create a new library at the specified directory"""
        library_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        images_dir = library_dir / "images"
        images_dir.mkdir(exist_ok=True)

        projects_dir = library_dir / "projects"
        projects_dir.mkdir(exist_ok=True)

        # Create library.json
        library_file = library_dir / "library.json"

        library = cls(
            library_name=library_name,
            library_dir=library_dir,
            library_file=library_file,
            library_image_list=ImageList(images_dir),
            projects={},
            similar_images={},
            metadata={},
            active_caption_profile="",
            caption_profiles=[],
        )

        # Save initial library file
        library.save()

        return library
