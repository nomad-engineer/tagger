#!/usr/bin/env python3
"""
Test real mask behavior to identify remaining issues
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


def test_mask_real_behavior():
    """Test actual mask behavior with real operations"""
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

        print("=== Testing Real Mask Behavior ===")

        # Test 1: Clear mask behavior
        print("\n1. Testing Clear Mask:")
        dialog._clear_mask()
        mask_image = dialog.mask_image
        if mask_image:
            alpha = QColor.fromRgba(mask_image.pixel(0, 0)).alpha()
            print(f"   After clear, mask alpha: {alpha} (should be 0)")
            assert alpha == 0, f"Expected 0, got {alpha}"
            print("   ✅ Clear mask sets alpha=0 correctly")

        # Test 2: Raise background to 255%
        print("\n2. Testing Raise Background to 255%:")
        dialog.background_spin.setValue(100)  # 100% = alpha 255
        dialog._on_raise_background_clicked()
        mask_image = dialog.mask_image
        if mask_image:
            alpha = QColor.fromRgba(mask_image.pixel(0, 0)).alpha()
            print(f"   After raise to 100%, mask alpha: {alpha} (should be 255)")
            assert alpha == 255, f"Expected 255, got {alpha}"
            print("   ✅ Raise to 100% sets alpha=255 correctly")

        # Test 3: Raise background to 120% (should cap at 100%)
        print("\n3. Testing Raise Background to 120% (should cap at 100%):")
        dialog.background_spin.setValue(120)  # 120% should cap at 100%
        print(
            f"   Spinbox value after setting to 120: {dialog.background_spin.value()}"
        )
        dialog._on_raise_background_clicked()
        mask_image = dialog.mask_image
        if mask_image:
            alpha = QColor.fromRgba(mask_image.pixel(0, 0)).alpha()
            print(f"   After raise to 120%, mask alpha: {alpha} (should be 255)")
            assert alpha >= 254, (
                f"Expected >=254, got {alpha}"
            )  # Allow for precision issues
            print("   ✅ Raise to 120% caps at alpha=255 correctly")

        # Test 4: Raise background to 50% (should be ~128)
        print("\n4. Testing Raise Background to 50%:")
        dialog.background_spin.setValue(50)  # 50% = alpha 128
        dialog._on_raise_background_clicked()
        mask_image = dialog.mask_image
        if mask_image:
            alpha = QColor.fromRgba(mask_image.pixel(0, 0)).alpha()
            expected_alpha = 128  # 50% of 255
            print(
                f"   After raise to 50%, mask alpha: {alpha} (should be ~{expected_alpha})"
            )
            assert alpha >= 125 and alpha <= 130, (
                f"Expected ~{expected_alpha}, got {alpha}"
            )
            print("   ✅ Raise to 50% sets alpha=~128 correctly")

        # Test 5: Paint behavior (simulate painting)
        print("\n5. Testing Paint Behavior:")
        # Clear first
        dialog._clear_mask()

        # Simulate painting at center
        from PyQt5.QtCore import QPoint

        center_point = QPoint(50, 50)
        dialog.mask_widget._draw_point(center_point)

        # Force mask update
        dialog.mask_widget.mask_changed.emit(dialog.mask_widget.get_mask_image())

        mask_image = dialog.mask_image
        if mask_image:
            # Check painted area (around center)
            painted_alpha = QColor.fromRgba(mask_image.pixel(50, 50)).alpha()
            print(f"   Painted point alpha: {painted_alpha} (should be 255)")
            assert painted_alpha == 255, f"Expected 255, got {painted_alpha}"
            print("   ✅ Paint sets alpha=255 correctly")

            # Check unpainted area
            unpainted_alpha = QColor.fromRgba(mask_image.pixel(10, 10)).alpha()
            print(f"   Unpainted point alpha: {unpainted_alpha} (should be 0)")
            assert unpainted_alpha == 0, f"Expected 0, got {unpainted_alpha}"
            print("   ✅ Unpainted area remains alpha=0")

        # Test 6: Apply mask and check preview
        print("\n6. Testing Apply Mask:")
        dialog._apply_mask()
        print("   ✅ Apply mask completed without errors")

        # Test 7: Background spinbox behavior
        print("\n7. Testing Background Spinbox:")
        print(f"   Current value: {dialog.background_spin.value()}")
        print(f"   Current text: '{dialog.background_spin.text()}'")
        print(f"   Current suffix: '{dialog.background_spin.suffix()}'")

        # Test value changes
        dialog.background_spin.setValue(25)
        print(f"   After setValue(25): '{dialog.background_spin.text()}'")
        assert dialog.background_spin.text() == "25%", (
            f"Expected '25%', got '{dialog.background_spin.text()}'"
        )
        print("   ✅ Background spinbox shows percentage correctly")

        # Clean up
        dialog.close()

    finally:
        # Delete temporary image
        image_path.unlink(missing_ok=True)

    print("\n🎉 All real mask behavior tests passed!")


if __name__ == "__main__":
    test_mask_real_behavior()
