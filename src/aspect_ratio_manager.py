"""
Aspect Ratio Manager - Handles persistence of crop aspect ratio preferences
"""

from typing import Dict, Tuple, Optional
from .app_manager import AppManager


class AspectRatioManager:
    """Manages aspect ratio preferences for cropping functionality"""

    # SDXL aspect ratios (width, height)
    SDXL_ASPECTS = {
        "Square (1:1)": (1024, 1024),
        "Landscape (4:3)": (1152, 896),
        "Landscape (3:2)": (1216, 832),
        "Landscape (16:9)": (1344, 768),
        "Portrait (3:4)": (896, 1152),
        "Portrait (2:3)": (832, 1216),
        "Portrait (9:16)": (768, 1344),
        "Auto": None,  # Free aspect ratio
    }

    def __init__(self, app_manager: AppManager):
        self.app_manager = app_manager

    def get_default_aspect_ratio(self) -> str:
        """Get library's default aspect ratio for cropping"""
        library = self.app_manager.get_library()
        if not library:
            return "Auto"

        return library.metadata.get("default_crop_aspect_ratio", "Auto")

    def set_default_aspect_ratio(self, aspect_ratio: str) -> bool:
        """
        Set and persist library's default aspect ratio

        Args:
            aspect_ratio: Aspect ratio name from SDXL_ASPECTS

        Returns:
            True if successfully saved, False otherwise
        """
        library = self.app_manager.get_library()
        if not library:
            return False

        # Validate aspect ratio
        if aspect_ratio not in self.SDXL_ASPECTS:
            return False

        # Update library metadata
        if "metadata" not in library.__dict__ or library.metadata is None:
            library.metadata = {}

        library.metadata["default_crop_aspect_ratio"] = aspect_ratio

        # Save library
        try:
            library.save()
            return True
        except Exception:
            return False

    def get_aspect_ratio_dimensions(
        self, aspect_ratio: str
    ) -> Optional[Tuple[int, int]]:
        """
        Get width/height dimensions for an aspect ratio

        Args:
            aspect_ratio: Aspect ratio name

        Returns:
            (width, height) tuple or None for auto
        """
        return self.SDXL_ASPECTS.get(aspect_ratio)

    def get_available_aspect_ratios(self) -> Dict[str, Optional[Tuple[int, int]]]:
        """Get all available aspect ratios"""
        return self.SDXL_ASPECTS.copy()

    def is_fixed_aspect_ratio(self, aspect_ratio: str) -> bool:
        """Check if aspect ratio is fixed (not auto)"""
        dimensions = self.SDXL_ASPECTS.get(aspect_ratio)
        return dimensions is not None

    def calculate_aspect_ratio(self, width: int, height: int) -> str:
        """
        Calculate the aspect ratio name that best matches the given dimensions

        Args:
            width: Width in pixels
            height: Height in pixels

        Returns:
            Closest aspect ratio name
        """
        if width <= 0 or height <= 0:
            return "Auto"

        # Calculate ratio
        ratio = width / height

        # Find closest match
        closest_ratio = "Auto"
        min_diff = float("inf")

        for name, dimensions in self.SDXL_ASPECTS.items():
            if dimensions is None:
                continue

            w, h = dimensions
            aspect_diff = abs((w / h) - ratio)

            if aspect_diff < min_diff:
                min_diff = aspect_diff
                closest_ratio = name

        return closest_ratio
