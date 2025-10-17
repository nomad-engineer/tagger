"""
Tests for utility functions
"""
import pytest
from pathlib import Path
import tempfile
import hashlib
from src.utils import hash_image, fuzzy_search, parse_filter_expression, parse_export_template, apply_export_template
from src.data_models import ImageData, Tag


def test_hash_image():
    """Test image hashing"""
    # Create a temporary image file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as f:
        f.write(b'fake image data')
        temp_path = Path(f.name)

    try:
        # Test default hash length
        hash1 = hash_image(temp_path, 16)
        assert len(hash1) == 16

        # Test different hash length
        hash2 = hash_image(temp_path, 8)
        assert len(hash2) == 8

        # Same file should produce same hash
        hash3 = hash_image(temp_path, 16)
        assert hash1 == hash3

    finally:
        temp_path.unlink()


def test_fuzzy_search():
    """Test fuzzy search functionality"""
    candidates = [
        "setting:mountain",
        "setting:beach",
        "camera:from front",
        "camera:from back",
        "details:sunny day"
    ]

    # Exact match
    results = fuzzy_search("mountain", candidates)
    assert len(results) > 0
    assert results[0][0] == "setting:mountain"

    # Partial match
    results = fuzzy_search("cam", candidates)
    assert len(results) >= 2
    assert all("camera" in r[0] for r in results[:2])

    # No query returns all
    results = fuzzy_search("", candidates)
    assert len(results) == len(candidates)


def test_parse_filter_expression():
    """Test filter expression parsing"""
    # Simple AND
    result = parse_filter_expression("tag1 AND tag2")
    assert "tag1" in result["include"]
    assert "tag2" in result["include"]
    assert len(result["exclude"]) == 0

    # With NOT
    result = parse_filter_expression("tag1 AND tag2 NOT tag3")
    assert "tag1" in result["include"]
    assert "tag2" in result["include"]
    assert "tag3" in result["exclude"]

    # Multiple NOT
    result = parse_filter_expression("tag1 NOT tag2 NOT tag3")
    assert "tag1" in result["include"]
    assert "tag2" in result["exclude"]
    assert "tag3" in result["exclude"]


def test_parse_export_template():
    """Test export template parsing"""
    # Simple template
    template = "trigger, {class}, {camera}"
    parts = parse_export_template(template)

    assert len(parts) == 3
    assert parts[0]["type"] == "literal"
    assert parts[0]["value"] == "trigger"
    assert parts[1]["type"] == "category"
    assert parts[1]["category"] == "class"
    assert parts[2]["type"] == "category"
    assert parts[2]["category"] == "camera"

    # With range
    template = "{details}[0:3]"
    parts = parse_export_template(template)

    assert len(parts) == 1
    assert parts[0]["type"] == "category"
    assert parts[0]["category"] == "details"
    assert parts[0]["range"] == "0:3"


def test_apply_export_template():
    """Test applying export template to image data"""
    # Create image data
    img_data = ImageData(
        name="test",
        caption="",
        tags=[
            Tag("class", "person"),
            Tag("camera", "from front"),
            Tag("details", "smiling"),
            Tag("details", "outdoors"),
            Tag("details", "sunny")
        ]
    )

    # Simple template
    template = "trigger, {class}"
    parts = parse_export_template(template)
    result = apply_export_template(parts, img_data)
    assert result == "trigger, person"

    # With range
    template = "{class}, {details}[0:2]"
    parts = parse_export_template(template)
    result = apply_export_template(parts, img_data)
    assert result == "person, smiling, outdoors"

    # Multiple categories
    template = "{class}, {camera}, {details}"
    parts = parse_export_template(template)
    result = apply_export_template(parts, img_data)
    assert "person" in result
    assert "from front" in result
    assert "smiling" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
