"""
Tests for utility functions
"""
import pytest
from pathlib import Path
import tempfile
from PIL import Image
from src.utils import (
    hash_image,
    fuzzy_search,
    parse_export_template,
    apply_export_template,
)


def make_test_image(path: Path, color: str = "red"):
    img = Image.new("RGB", (64, 64), color=color)
    img.save(path)


def test_hash_image():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "test.png"
        make_test_image(p)

        h1 = hash_image(p, 16)
        assert len(h1) == 16
        assert h1 == hash_image(p, 16)   # deterministic

        h8 = hash_image(p, 8)
        assert len(h8) == 8


def test_hash_image_different_images():
    with tempfile.TemporaryDirectory() as tmpdir:
        p1 = Path(tmpdir) / "red.png"
        p2 = Path(tmpdir) / "blue.png"
        make_test_image(p1, "red")
        make_test_image(p2, "blue")
        assert hash_image(p1, 16) != hash_image(p2, 16)


def test_fuzzy_search_empty_query():
    candidates = ["solo", "blue_hair", "outdoors"]
    results = fuzzy_search("", candidates)
    assert len(results) == len(candidates)


def test_fuzzy_search_match():
    candidates = ["solo", "blue_hair", "1girl", "outdoors"]
    results = fuzzy_search("blue", candidates)
    assert len(results) >= 1
    assert results[0][0] == "blue_hair"


def test_fuzzy_search_no_match():
    candidates = ["solo", "blue_hair"]
    results = fuzzy_search("xxxxxx", candidates)
    assert len(results) == 0


def test_parse_export_template_literal_and_category():
    parts = parse_export_template("trigger, {character}")
    assert parts[0]["type"] == "literal"
    assert parts[0]["value"] == "trigger, "
    assert parts[1]["type"] == "category"
    assert parts[1]["category"] == "character"
    assert parts[1]["range"] is None


def test_parse_export_template_with_range():
    parts = parse_export_template("{details}[0:3]")
    assert len(parts) == 1
    assert parts[0]["type"] == "category"
    assert parts[0]["category"] == "details"
    assert parts[0]["range"] == "0:3"


def test_parse_export_template_multiple_categories():
    parts = parse_export_template("{character}, {setting}, {pose}")
    category_parts = [p for p in parts if p["type"] == "category"]
    assert len(category_parts) == 3
    cats = [p["category"] for p in category_parts]
    assert "character" in cats
    assert "setting" in cats
    assert "pose" in cats


def test_apply_export_template_with_taxonomy():
    taxonomy = {
        "1girl": "character",
        "solo": "character",
        "blue_hair": "appearance",
        "outdoors": "setting",
        "smiling": "pose",
    }
    tags = ["1girl", "solo", "blue_hair", "outdoors", "smiling"]
    parts = parse_export_template("trigger, {character}, {setting}")
    result = apply_export_template(parts, tags, taxonomy=taxonomy)
    assert "1girl" in result
    assert "solo" in result
    assert "outdoors" in result
    # appearance and pose not in template
    assert "blue_hair" not in result
    assert "smiling" not in result


def test_apply_export_template_range():
    taxonomy = {"a": "detail", "b": "detail", "c": "detail", "d": "detail"}
    tags = ["a", "b", "c", "d"]
    parts = parse_export_template("{detail}[0:2]")
    result = apply_export_template(parts, tags, taxonomy=taxonomy)
    assert "a" in result
    assert "b" in result
    assert "c" not in result
    assert "d" not in result


def test_apply_export_template_remove_duplicates():
    taxonomy = {"tag1": "cat", "tag2": "cat"}
    tags = ["tag1", "tag2", "tag1"]   # tag1 appears twice
    parts = parse_export_template("{cat}")
    result = apply_export_template(parts, tags, taxonomy=taxonomy, remove_duplicates=True)
    assert result.count("tag1") == 1


def test_apply_export_template_no_taxonomy():
    # Without taxonomy, all category placeholders produce empty output
    parts = parse_export_template("trigger, {character}")
    result = apply_export_template(parts, ["1girl", "solo"])
    # "trigger, " with no characters → just "trigger"
    assert "trigger" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
