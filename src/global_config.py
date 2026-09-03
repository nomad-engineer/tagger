"""
Global configuration dataclass - extracted to avoid PyQt5 import chain.
Used by both config_manager.py and data_models.py.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from pathlib import Path
import json


@dataclass
class GlobalConfig:
    """Global application configuration (global.json)"""

    hash_length: int = 16
    thumbnail_size: int = 150
    libraries_root: str = str(Path.home() / "tagger-libraries")
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
            "libraries_root": self.libraries_root,
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
