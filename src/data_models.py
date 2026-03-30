"""
Simplified data models for the tagger application.

Tags are flat strings (no categories).
Captions are named dictionaries (multiple caption slots per image).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
from .global_config import GlobalConfig  # Re-export for convenience


@dataclass
class MediaData:
    """
    Represents a single media item (image or video).

    Data is stored in SQLite (primary) and exported as JSON sidecars.
    """

    name: str = ""
    media_type: str = "image"              # "image" or "video"
    captions: Dict[str, str] = field(default_factory=dict)   # label -> caption text
    tags: List[str] = field(default_factory=list)             # flat tag strings
    related: Dict[str, List[str]] = field(default_factory=dict)  # rel_type -> [hashes]

    # -----------------------------------------------------------------------
    # Caption helpers
    # -----------------------------------------------------------------------

    def get_caption(self, label: str = "default") -> str:
        return self.captions.get(label, "")

    def set_caption(self, content: str, label: str = "default"):
        if content:
            self.captions[label] = content
        else:
            self.captions.pop(label, None)

    # -----------------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "media_type": self.media_type,
            "captions": self.captions,
            "tags": self.tags,
            "related": self.related,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaData":
        captions = data.get("captions", {})
        if not isinstance(captions, dict):
            captions = {}

        tags = data.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        # Ensure all tags are strings
        tags = [str(t) for t in tags if t]

        return cls(
            name=data.get("name", ""),
            media_type=data.get("media_type", "image"),
            captions=captions,
            tags=tags,
            related=data.get("related", {}),
        )
