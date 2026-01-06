#!/usr/bin/env python3
"""
Test default mask state in CropMaskDialog
"""

import sys
import tempfile
from pathlib import Path
from PIL import Image
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QColor

# Add src to path
sys.path.insert(0, ".")


# Mock app manager
class MockAppManager:
    def __init__(self):
        self.library = None
        self._image_data_cache = {}
        self.fs_repo = None
        self.db_repo = None

    def get_library(self):
        return None

    def get_tag_list(self):
        return None

    def get_config(self):
        return {}

    def get_library_path(self):
        return None

    def get_current_view(self):
        return None

    def get_project(self):
        return None

    def get_tag_list(self):
        return None


def test_default_mask():
    """Test that default mask is fully opaque (alpha=255)"""
    # Create QApplication instance (required for Qt widgets)
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Create a temporary test image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img = Image.new("RGB", (100, 100), color="red")
        img.save(f.name, "PNG")
        image_path = Path(f.name)

    try:
        # Import dialog
        from src.crop_mask_dialog import CropMaskDialog

        # Create dialog (parent None)
        dialog = CropMaskDialog(MockAppManager(), image_path, parent=None)

        # Dialog loads image and initializes default state
        # Check mask image
        mask_image = dialog.mask_image
        assert mask_image is not None, "Mask image should be initialized"
        assert mask_image.width() == 100, (
            f"Mask width should match image, got {mask_image.width()}"
        )
        assert mask_image.height() == 100, (
            f"Mask height should match image, got {mask_image.height()}"
        )

        # Check that mask is fully opaque (alpha=255 everywhere)
        # Sample a few pixels
        for x in [0, 50, 99]:
            for y in [0, 50, 99]:
                alpha = QColor.fromRgba(mask_image.pixel(x, y)).alpha()
                assert alpha == 255, (
                    f"Pixel ({x},{y}) should have alpha 255, got {alpha}"
                )

        print("✅ Default mask test passed: mask is fully opaque")

        # Test clear mask
        print(
            f"Before clear, dialog.mask_image alpha: {QColor.fromRgba(dialog.mask_image.pixel(0, 0)).alpha()}"
        )
        dialog._clear_mask()
        mask_image = dialog.mask_image
        assert mask_image is not None
        # After clear, mask should be transparent (alpha=0)
        alpha = QColor.fromRgba(mask_image.pixel(0, 0)).alpha()
        print(f"After clear, dialog.mask_image alpha: {alpha}")
        # Also check mask_widget's mask
        widget_mask = dialog.mask_widget.get_mask_image()
        if widget_mask:
            widget_alpha = QColor.fromRgba(widget_mask.pixel(0, 0)).alpha()
            print(f"After clear, widget mask alpha: {widget_alpha}")
        assert alpha == 0, f"After clear, pixel alpha should be 0, got {alpha}"
        print("✅ Clear mask test passed: mask is transparent")

        # Test raise background
        dialog.background_spin.setValue(30)
        dialog._on_raise_background_clicked()
        mask_image = dialog.mask_image
        alpha = QColor.fromRgba(mask_image.pixel(0, 0)).alpha()
        assert alpha == 30, (
            f"After raise background, pixel alpha should be 30, got {alpha}"
        )
        print("✅ Raise background test passed: mask alpha increased")

        # Clean up
        dialog.close()

    finally:
        # Delete temporary image
        image_path.unlink(missing_ok=True)

    print("\n🎉 All mask default state tests passed!")


if __name__ == "__main__":
    test_default_mask()
