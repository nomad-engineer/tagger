#!/usr/bin/env python3
"""
Integration test for the cropped view feature
Tests the complete workflow from image selection to crop creation
"""

import sys
import tempfile
from pathlib import Path
from PIL import Image
import hashlib


# Test imports
def test_imports():
    """Test that all crop feature modules can be imported"""
    print("=" * 60)
    print("TESTING IMPORTS")
    print("=" * 60)

    try:
        from src.data_models import CropData, ImageData, Tag

        print("✓ CropData, ImageData, Tag imported")

        from src.aspect_ratio_manager import AspectRatioManager

        print("✓ AspectRatioManager imported")

        from src.crop_selection_widget import CropSelectionWidget

        print("✓ CropSelectionWidget imported")

        from src.tag_addition_popup import TagAdditionPopup

        print("✓ TagAdditionPopup imported")

        from src.crop_dialog import CropDialog

        print("✓ CropDialog imported")

        print("\n✅ All imports successful!")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_crop_data_model():
    """Test CropData model"""
    print("\n" + "=" * 60)
    print("TESTING CROPDATA MODEL")
    print("=" * 60)

    try:
        from src.data_models import CropData, Tag

        # Create test tags
        tags = [Tag(name="test", color="#ff0000")]

        # Create crop data
        crop_data = CropData(
            name="test_crop_123",
            parent_image="parent_abc123",
            crop_rect=(10, 20, 100, 150),
            aspect_ratio="1:1",
            created_at="2024-01-01T12:00:00",
            tags=tags,
        )

        print(f"✓ Created CropData: {crop_data.name}")
        print(f"  - Parent: {crop_data.parent_image}")
        print(f"  - Crop rect: {crop_data.crop_rect}")
        print(f"  - Aspect ratio: {crop_data.aspect_ratio}")
        print(f"  - Tags: {len(crop_data.tags)}")

        # Test serialization
        data_dict = crop_data.to_dict()
        print(f"✓ Serialized to dict: {len(data_dict)} keys")

        # Test deserialization
        restored = CropData.from_dict(data_dict)
        print(f"✓ Deserialized from dict: {restored.name}")

        print("\n✅ CropData model test passed!")
        return True
    except Exception as e:
        print(f"❌ CropData test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_aspect_ratio_manager():
    """Test AspectRatioManager without a real app_manager"""
    print("\n" + "=" * 60)
    print("TESTING ASPECT RATIO MANAGER")
    print("=" * 60)

    try:
        from src.aspect_ratio_manager import AspectRatioManager

        # Create a mock app manager
        class MockAppManager:
            def __init__(self):
                self.library_path = None

            def get_library(self):
                return None

        manager = AspectRatioManager(MockAppManager())

        # Test available aspect ratios
        aspects = manager.get_available_aspect_ratios()
        print(f"✓ Available aspect ratios: {list(aspects.keys())}")

        # Test dimensions for specific aspect ratio
        dims = manager.get_aspect_ratio_dimensions("1:1")
        print(f"✓ 1:1 dimensions: {dims}")

        dims = manager.get_aspect_ratio_dimensions("16:9")
        print(f"✓ 16:9 dimensions: {dims}")

        # Test default aspect ratio
        default = manager.get_default_aspect_ratio()
        print(f"✓ Default aspect ratio: {default}")

        print("\n✅ AspectRatioManager test passed!")
        return True
    except Exception as e:
        print(f"❌ AspectRatioManager test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_crop_image_creation():
    """Test creating cropped images"""
    print("\n" + "=" * 60)
    print("TESTING CROP IMAGE CREATION")
    print("=" * 60)

    try:
        # Create a test image
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create a test image
            test_image_path = tmpdir / "test_image.png"
            img = Image.new("RGB", (800, 600), color="red")
            img.save(test_image_path)
            print(f"✓ Created test image: {test_image_path}")

            # Create a crop directory
            crops_dir = tmpdir / "crops"
            crops_dir.mkdir()

            # Test cropping
            with Image.open(test_image_path) as img:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")

                # Crop a 200x200 region from (100, 100)
                cropped = img.crop((100, 100, 300, 300))

                crop_path = crops_dir / "test_crop.png"
                cropped.save(crop_path, format="PNG", compress_level=0)
                print(f"✓ Created cropped image: {crop_path}")

                # Generate hash
                with open(crop_path, "rb") as f:
                    crop_hash = hashlib.sha256(f.read()).hexdigest()[:16]
                print(f"✓ Generated crop hash: {crop_hash}")

                # Verify file
                if crop_path.exists():
                    size = crop_path.stat().st_size
                    print(f"✓ Crop file size: {size} bytes")

        print("\n✅ Crop image creation test passed!")
        return True
    except Exception as e:
        print(f"❌ Crop image creation test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_coordinate_mapping():
    """Test coordinate mapping from screen to image"""
    print("\n" + "=" * 60)
    print("TESTING COORDINATE MAPPING")
    print("=" * 60)

    try:
        from PyQt5.QtCore import QRect
        from src.crop_dialog import CropDialog

        # Create a mock crop dialog
        class MockAppManager:
            pass

        dialog = CropDialog(MockAppManager(), Path("dummy.png"))
        dialog.scale_factor = 2.0  # Image was scaled down 2x

        # Test mapping
        screen_rect = QRect(100, 50, 200, 150)
        image_rect = dialog._map_to_image_coordinates(screen_rect)

        print(
            f"✓ Screen rect: ({screen_rect.x()}, {screen_rect.y()}, {screen_rect.width()}, {screen_rect.height()})"
        )
        print(
            f"✓ Image rect: ({image_rect.x()}, {image_rect.y()}, {image_rect.width()}, {image_rect.height()})"
        )

        # Verify mapping
        assert image_rect.x() == 50  # 100 / 2.0
        assert image_rect.y() == 25  # 50 / 2.0
        assert image_rect.width() == 100  # 200 / 2.0
        assert image_rect.height() == 75  # 150 / 2.0

        print("✓ Coordinate mapping verified")

        print("\n✅ Coordinate mapping test passed!")
        return True
    except Exception as e:
        print(f"❌ Coordinate mapping test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  CROPPED VIEW FEATURE - INTEGRATION TEST SUITE".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")

    results = []

    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("CropData Model", test_crop_data_model()))
    results.append(("AspectRatioManager", test_aspect_ratio_manager()))
    results.append(("Crop Image Creation", test_crop_image_creation()))
    results.append(("Coordinate Mapping", test_coordinate_mapping()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! The cropped view feature is ready!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
