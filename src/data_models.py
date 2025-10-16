"""
Shared data models used across the application
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
import json


@dataclass
class AppConfig:
    """Global application configuration"""
    theme: str = "default"
    window_mode: str = "single"  # single, multi
    recent_projects: List[str] = field(default_factory=list)
    default_image_extensions: List[str] = field(default_factory=lambda: [".jpg", ".jpeg", ".png", ".bmp", ".gif"])
    autosave_interval: int = 300  # seconds
    max_recent_projects: int = 10
    custom_settings: Dict[str, Any] = field(default_factory=dict)
    
    def save(self, path: Path):
        """Save configuration to file"""
        with open(path, 'w') as f:
            json.dump(self.__dict__, f, indent=2, default=str)
    
    @classmethod
    def load(cls, path: Path) -> 'AppConfig':
        """Load configuration from file"""
        if path.exists():
            with open(path, 'r') as f:
                data = json.load(f)
                return cls(**data)
        return cls()


@dataclass
class ProjectData:
    """
    Project-specific data

    Stored in user-selected .json file
    """
    project_name: str = ""
    project_file: Optional[Path] = None  # Path to the .json project file
    images: List[str] = field(default_factory=list)  # Relative paths to images
    metadata: Dict[str, Any] = field(default_factory=dict)  # Custom project metadata

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
                'images': self.images,
                'metadata': self.metadata
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
                    project_file=project_file,
                    images=data.get('images', []),
                    metadata=data.get('metadata', {})
                )
        return cls(project_file=project_file)

    def get_absolute_image_path(self, relative_path: str) -> Optional[Path]:
        """Convert relative image path to absolute path"""
        base_dir = self.get_base_directory()
        if base_dir:
            return base_dir / relative_path
        return None

    def get_all_absolute_image_paths(self) -> List[Path]:
        """Get all images as absolute paths"""
        base_dir = self.get_base_directory()
        if base_dir:
            return [base_dir / img for img in self.images]
        return []

    def add_image(self, image_path: Path) -> bool:
        """Add image to project if not already present"""
        base_dir = self.get_base_directory()
        if not base_dir:
            return False

        try:
            rel_path = str(image_path.relative_to(base_dir))
            if rel_path not in self.images:
                self.images.append(rel_path)
                return True
        except ValueError:
            # Image not relative to base directory
            pass
        return False


@dataclass
class ImageSelectionData:
    """Current image selection and editing state"""
    selected_images: List[Path] = field(default_factory=list)
    current_image_index: int = 0
    current_image_path: Optional[Path] = None
    current_annotations: Dict[str, Any] = field(default_factory=dict)
    selection_history: List[Path] = field(default_factory=list)
    modified: bool = False
    
    def select_image(self, image_path: Path):
        """Select a single image"""
        self.current_image_path = image_path
        if image_path not in self.selected_images:
            self.selected_images.append(image_path)
        self.current_image_index = self.selected_images.index(image_path)
        self.selection_history.append(image_path)
    
    def select_multiple(self, image_paths: List[Path]):
        """Select multiple images"""
        self.selected_images = image_paths
        if image_paths:
            self.current_image_path = image_paths[0]
            self.current_image_index = 0
    
    def next_image(self) -> Optional[Path]:
        """Move to next image in selection"""
        if self.selected_images and self.current_image_index < len(self.selected_images) - 1:
            self.current_image_index += 1
            self.current_image_path = self.selected_images[self.current_image_index]
            return self.current_image_path
        return None
    
    def previous_image(self) -> Optional[Path]:
        """Move to previous image in selection"""
        if self.selected_images and self.current_image_index > 0:
            self.current_image_index -= 1
            self.current_image_path = self.selected_images[self.current_image_index]
            return self.current_image_path
        return None
    
    def clear_selection(self):
        """Clear all selections"""
        self.selected_images.clear()
        self.current_image_path = None
        self.current_image_index = 0
        self.current_annotations.clear()
        self.modified = False