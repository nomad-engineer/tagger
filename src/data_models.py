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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hash_length": self.hash_length,
            "thumbnail_size": self.thumbnail_size,
            "default_import_tag_category": self.default_import_tag_category,
            "default_image_extensions": self.default_image_extensions,
            "recent_projects": self.recent_projects,
            "max_recent_projects": self.max_recent_projects
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
    images: List[Dict[str, str]] = field(default_factory=list)  # List of {"path": "rel/path/to/image.png"}
    export: Dict[str, Any] = field(default_factory=dict)  # Export profiles and settings
    filters: Dict[str, Any] = field(default_factory=dict)  # Saved filters
    preferences: Dict[str, Any] = field(default_factory=dict)  # Project-specific preference overrides

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
                'images': self.images,
                'export': self.export,
                'filters': self.filters,
                'preferences': self.preferences
            }
            with open(self.project_file, 'w') as f:
                json.dump(data, f, indent=2)

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
                return cls(
                    project_name=data.get('project_name', ''),
                    description=data.get('description', ''),
                    project_file=project_file,
                    images=data.get('images', []),
                    export=data.get('export', {}),
                    filters=data.get('filters', {}),
                    preferences=data.get('preferences', {})
                )
        return cls(project_file=project_file)

    def get_absolute_image_path(self, relative_path: str) -> Optional[Path]:
        """Convert relative image path to absolute path"""
        base_dir = self.get_base_directory()
        if base_dir:
            return base_dir / relative_path
        return None

    def get_all_image_paths(self) -> List[str]:
        """Get all image paths (relative)"""
        return [img.get("path", "") for img in self.images if img.get("path")]

    def get_all_absolute_image_paths(self) -> List[Path]:
        """Get all images as absolute paths"""
        base_dir = self.get_base_directory()
        if base_dir:
            return [base_dir / img.get("path") for img in self.images if img.get("path")]
        return []

    def add_image(self, image_path: Path) -> bool:
        """Add image to project if not already present"""
        base_dir = self.get_base_directory()
        if not base_dir:
            return False

        try:
            rel_path = str(image_path.relative_to(base_dir))
            # Check if already exists
            if not any(img.get("path") == rel_path for img in self.images):
                self.images.append({"path": rel_path})
                return True
        except ValueError:
            # Image not relative to base directory
            pass
        return False

    def remove_image(self, image_path: Path) -> bool:
        """Remove image from project"""
        base_dir = self.get_base_directory()
        if not base_dir:
            return False

        try:
            rel_path = str(image_path.relative_to(base_dir))
            # Find and remove the image
            for img in self.images:
                if img.get("path") == rel_path:
                    self.images.remove(img)
                    return True
        except ValueError:
            # Image not relative to base directory
            pass
        return False

    def get_image_json_path(self, image_path: Path) -> Path:
        """Get the .json path for an image"""
        return image_path.with_suffix('.json')


@dataclass
class ImageSelectionData:
    """Current image selection and editing state"""
    selected_images: List[Path] = field(default_factory=list)  # Images with checkboxes selected
    active_image: Optional[Path] = None  # Currently focused image
    filtered_images: Optional[List[Path]] = None  # Images after filter is applied (None = no filter)

    def set_active(self, image_path: Path):
        """Set the active (focused) image"""
        self.active_image = image_path

    def toggle_selection(self, image_path: Path):
        """Toggle selection checkbox for an image"""
        if image_path in self.selected_images:
            self.selected_images.remove(image_path)
        else:
            self.selected_images.append(image_path)

    def select_all(self, image_paths: List[Path]):
        """Select all images"""
        self.selected_images = image_paths.copy()

    def clear_selection(self):
        """Clear all selected images"""
        self.selected_images.clear()

    def get_working_images(self) -> List[Path]:
        """Get images to work on: selected images if any, otherwise active image"""
        if self.selected_images:
            return self.selected_images
        elif self.active_image:
            return [self.active_image]
        return []