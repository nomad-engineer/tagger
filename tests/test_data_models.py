"""
Tests for data models
"""
import pytest
from src.data_models import MediaData, GlobalConfig


def test_media_data_defaults():
    m = MediaData()
    assert m.name == ""
    assert m.media_type == "image"
    assert m.tags == []
    assert m.captions == {}
    assert m.related == {}


def test_media_data_tags():
    m = MediaData(name="test", tags=["solo", "blue_hair", "outdoors"])
    assert len(m.tags) == 3
    assert "solo" in m.tags
    assert "blue_hair" in m.tags


def test_media_data_captions():
    m = MediaData(captions={"default": "solo, blue hair", "kohya": "trigger, solo"})
    assert m.captions["default"] == "solo, blue hair"
    assert m.captions["kohya"] == "trigger, solo"
    assert m.captions.get("missing") is None


def test_media_data_get_caption():
    m = MediaData(captions={"default": "solo, blue hair"})
    assert m.get_caption("default") == "solo, blue hair"
    assert m.get_caption("nonexistent") == ""


def test_media_data_related():
    m = MediaData(related={"crop": ["child_hash"], "similar": ["other_hash"]})
    assert m.related["crop"] == ["child_hash"]
    assert m.related["similar"] == ["other_hash"]


def test_global_config():
    config = GlobalConfig(hash_length=16, thumbnail_size=150)
    assert config.hash_length == 16
    assert config.thumbnail_size == 150


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
