"""
Integration tests for the complete workflow
"""
import pytest
from pathlib import Path
import tempfile
import shutil
from PIL import Image
import io

from src.data_models import ProjectData, GlobalConfig, ImageData, Tag
from src.utils import hash_image, parse_export_template, apply_export_template


def create_test_image(path: Path, color='red'):
    """Create a simple test image"""
    img = Image.new('RGB', (100, 100), color=color)
    img.save(path)


def test_complete_workflow():
    """Test the complete image tagging workflow"""
    # Create temporary directory for test
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 1. Create a new project
        from src.data_models import ImageList
        project_file = tmpdir / "project.json"
        project = ProjectData(
            project_name="Test Project",
            description="Integration test",
            project_file=project_file,
            image_list=ImageList(tmpdir)
        )
        project.save()

        # 2. Create test images (different colors to ensure different hashes)
        test_img1 = tmpdir / "test1.png"
        test_img2 = tmpdir / "test2.png"
        create_test_image(test_img1, color='red')
        create_test_image(test_img2, color='blue')

        # 3. Import images with hashing
        config = GlobalConfig(hash_length=16)

        for img_path in [test_img1, test_img2]:
            # Hash and rename
            img_hash = hash_image(img_path, config.hash_length)
            ext = img_path.suffix
            new_filename = f"{img_hash}{ext}"
            new_path = tmpdir / new_filename

            shutil.copy2(img_path, new_path)

            # Add to project
            project.image_list.add_image(new_path)

            # Create JSON file
            json_path = project.get_image_json_path(new_path)
            img_data = ImageData(name=img_hash)
            img_data.add_tag("meta", "imported: 2024-01-01")
            img_data.save(json_path)

        assert len(project.image_list) == 2

        # 4. Add tags to images
        for img in project.get_all_absolute_image_paths():
            json_path = project.get_image_json_path(img)
            img_data = ImageData.load(json_path)
            img_data.add_tag("class", "person")
            img_data.add_tag("setting", "outdoors")
            img_data.save(json_path)

        # 5. Filter images by tag
        filtered_images = []
        for img in project.get_all_absolute_image_paths():
            img_data = ImageData.load(project.get_image_json_path(img))
            tags_str = [str(tag) for tag in img_data.tags]

            # Check if has "person" tag
            if any("person" in tag for tag in tags_str):
                filtered_images.append(img)

        assert len(filtered_images) == 2

        # 6. Export caption files
        export_template = "{class}, {setting}"
        template_parts = parse_export_template(export_template)

        for img in project.get_all_absolute_image_paths():
            img_data = ImageData.load(project.get_image_json_path(img))
            caption = apply_export_template(template_parts, img_data)

            # Write caption file
            caption_path = img.with_suffix('.txt')
            with open(caption_path, 'w') as f:
                f.write(caption)

            # Verify caption was created
            assert caption_path.exists()

            # Verify caption content
            with open(caption_path, 'r') as f:
                content = f.read()
                assert "person" in content
                assert "outdoors" in content

        # 7. Save and reload project
        project.save()

        loaded_project = ProjectData.load(project_file)
        assert loaded_project.project_name == "Test Project"
        assert len(loaded_project.image_list) == 2


def test_saved_filters_and_profiles():
    """Test saving and loading filters and export profiles"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        project_file = tmpdir / "project.json"
        project = ProjectData(
            project_name="Test",
            project_file=project_file
        )

        # Add saved filters
        project.filters["saved_filters"] = [
            "tag1 AND tag2",
            "tag3 NOT tag4"
        ]

        # Add export profiles
        project.export["saved_profiles"] = [
            "{class}, {camera}",
            "trigger, {class}, {details}[0:3]"
        ]

        # Save and reload
        project.save()

        loaded = ProjectData.load(project_file)
        assert len(loaded.filters["saved_filters"]) == 2
        assert len(loaded.export["saved_profiles"]) == 2
        assert "tag1 AND tag2" in loaded.filters["saved_filters"]
        assert "{class}, {camera}" in loaded.export["saved_profiles"]


def test_tag_modification():
    """Test adding, removing, and modifying tags"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create image and JSON
        img_path = tmpdir / "test.png"
        create_test_image(img_path)

        json_path = img_path.with_suffix('.json')
        img_data = ImageData(name="test")

        # Add tags
        img_data.add_tag("class", "person")
        img_data.add_tag("setting", "mountain")
        img_data.add_tag("camera", "from front")

        assert len(img_data.tags) == 3

        # Remove tag
        tag_to_remove = img_data.tags[1]  # "setting:mountain"
        img_data.remove_tag(tag_to_remove)

        assert len(img_data.tags) == 2

        # Get tags by category
        class_tags = img_data.get_tags_by_category("class")
        assert len(class_tags) == 1
        assert class_tags[0].value == "person"

        # Save and reload
        img_data.save(json_path)

        loaded = ImageData.load(json_path)
        assert len(loaded.tags) == 2
        assert not any(tag.category == "setting" for tag in loaded.tags)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
