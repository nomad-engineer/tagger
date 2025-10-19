"""
Tests for data models
"""
import pytest
from pathlib import Path
import tempfile
import json
from src.data_models import Tag, ImageData, GlobalConfig, ProjectData


def test_tag():
    """Test Tag model"""
    tag = Tag("setting", "mountain")
    assert str(tag) == "setting:mountain"

    # to_dict
    tag_dict = tag.to_dict()
    assert tag_dict["category"] == "setting"
    assert tag_dict["value"] == "mountain"

    # from_dict
    tag2 = Tag.from_dict({"category": "camera", "value": "from front"})
    assert tag2.category == "camera"
    assert tag2.value == "from front"


def test_image_data():
    """Test ImageData model"""
    # Create image data
    img_data = ImageData(name="test", caption="A test image")
    img_data.add_tag("setting", "mountain")
    img_data.add_tag("camera", "from front")

    assert len(img_data.tags) == 2

    # Get tags by category
    setting_tags = img_data.get_tags_by_category("setting")
    assert len(setting_tags) == 1
    assert setting_tags[0].value == "mountain"

    # Save and load
    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
        temp_path = Path(f.name)

    try:
        img_data.save(temp_path)
        assert temp_path.exists()

        loaded = ImageData.load(temp_path)
        assert loaded.name == "test"
        assert loaded.caption == "A test image"
        assert len(loaded.tags) == 2

    finally:
        temp_path.unlink()


def test_global_config():
    """Test GlobalConfig model"""
    config = GlobalConfig(
        hash_length=16,
        thumbnail_size=150,
        recent_projects=["project1.json", "project2.json"]
    )

    # Save and load
    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
        temp_path = Path(f.name)

    try:
        config.save(temp_path)
        assert temp_path.exists()

        loaded = GlobalConfig.load(temp_path)
        assert loaded.hash_length == 16
        assert loaded.thumbnail_size == 150
        assert len(loaded.recent_projects) == 2

    finally:
        temp_path.unlink()


def test_project_data():
    """Test ProjectData model"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
        temp_path = Path(f.name)

    try:
        # Create project with ImageList
        from src.data_models import ImageList
        base_dir = temp_path.parent
        project = ProjectData(
            project_name="Test Project",
            description="A test project",
            project_file=temp_path,
            image_list=ImageList(base_dir)
        )

        # Add image
        img_path = base_dir / "test_image.png"
        img_path.touch()

        project.image_list.add_image(img_path)
        assert len(project.image_list) == 1

        # Save and load
        project.save()
        assert temp_path.exists()

        loaded = ProjectData.load(temp_path)
        assert loaded.project_name == "Test Project"
        assert loaded.description == "A test project"
        assert len(loaded.image_list) == 1

        # Get absolute paths
        abs_paths = loaded.get_all_absolute_image_paths()
        assert len(abs_paths) == 1
        assert abs_paths[0].name == "test_image.png"

        img_path.unlink()

    finally:
        temp_path.unlink()


def test_project_export_filters():
    """Test project export and filter storage"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
        temp_path = Path(f.name)

    try:
        project = ProjectData(
            project_name="Test",
            project_file=temp_path
        )

        # Add export profiles
        project.export["saved_profiles"] = ["profile1", "profile2"]

        # Add filters
        project.filters["saved_filters"] = ["tag1 AND tag2", "tag3 NOT tag4"]

        # Add preferences
        project.preferences["hash_length"] = 8

        # Save and load
        project.save()

        loaded = ProjectData.load(temp_path)
        assert len(loaded.export["saved_profiles"]) == 2
        assert len(loaded.filters["saved_filters"]) == 2
        assert loaded.preferences["hash_length"] == 8

    finally:
        temp_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
