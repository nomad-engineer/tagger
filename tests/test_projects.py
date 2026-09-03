"""
Tests for dataset and export workflows.
"""
import pytest
from pathlib import Path
from PIL import Image

from src.web_app_manager import WebAppManager
from src.utils import parse_export_template, apply_export_template


def make_test_image(path: Path, color: str = "red"):
    img = Image.new("RGB", (64, 64), color=color)
    img.save(path)


@pytest.fixture
def manager(tmp_path):
    m = WebAppManager()
    m.create_new_library("Test Library", str(tmp_path))
    return m, tmp_path


def test_export_dataset(manager):
    mgr, library_dir = manager
    src = library_dir / "src"
    src.mkdir()
    make_test_image(src / "a.png", "red")
    make_test_image(src / "b.png", "blue")
    mgr.import_from_folder(str(src))

    lib_page = mgr.get_page(offset=0, limit=10)
    hashes = [item["hash"] for item in lib_page["items"]]

    # Set tags for export
    taxonomy = {"1girl": "character", "outdoors": "setting"}
    mgr.repo.add_tag(hashes[0], "1girl")
    mgr.repo.add_tag(hashes[0], "outdoors")

    # Assign taxonomy
    char_id = mgr.repo.upsert_category("character", 0, "#3b82f6")
    set_id = mgr.repo.upsert_category("setting", 1, "#22c55e")
    mgr.repo.set_tag_category("1girl", char_id)
    mgr.repo.set_tag_category("outdoors", set_id)

    # Create dataset and add one image
    mgr.create_dataset("export-test")
    mgr.load_dataset("export-test")
    mgr.add_images_to_dataset(hashes[:1])

    # Export
    output_dir = library_dir / "export_out"
    output_dir.mkdir()

    result = mgr.repo.conn.execute(
        "SELECT id FROM datasets WHERE name = 'export-test'"
    ).fetchone()
    assert result is not None

    # Verify taxonomy export
    tax_map = mgr.repo.get_taxonomy_map()
    image_tags = mgr.load_image_data(hashes[0])["tags"]
    parts = parse_export_template("{character}, {setting}")
    caption = apply_export_template(parts, image_tags, taxonomy=tax_map)
    assert "1girl" in caption
    assert "outdoors" in caption


def test_delete_dataset(manager):
    mgr, library_dir = manager
    mgr.create_dataset("to-delete")
    mgr.load_dataset("to-delete")

    datasets = mgr.repo.list_datasets()
    assert any(d["name"] == "to-delete" for d in datasets)

    ds = mgr.repo.get_dataset_by_name("to-delete")
    mgr.close_dataset()
    mgr.repo.delete_dataset(ds["id"])

    datasets = mgr.repo.list_datasets()
    assert not any(d["name"] == "to-delete" for d in datasets)


def test_caption_profile(manager):
    mgr, library_dir = manager
    mgr.create_dataset("profile-test")
    mgr.load_dataset("profile-test")

    ds = mgr.repo.get_dataset_by_name("profile-test")
    ok = mgr.repo.save_caption_profile(ds["id"], "{character}, {setting}", False, 0)
    assert ok

    row = mgr.repo.conn.execute(
        "SELECT template FROM dataset_caption_profiles WHERE dataset_id = ?",
        (ds["id"],)
    ).fetchone()
    assert row["template"] == "{character}, {setting}"


def test_set_repeats(manager):
    mgr, library_dir = manager
    src = library_dir / "src"
    src.mkdir()
    make_test_image(src / "img.png", "red")
    mgr.import_from_folder(str(src))

    lib_page = mgr.get_page(offset=0, limit=10)
    h = lib_page["items"][0]["hash"]

    mgr.create_dataset("repeats-test")
    mgr.load_dataset("repeats-test")
    mgr.add_images_to_dataset([h])

    ds = mgr.repo.get_dataset_by_name("repeats-test")
    ok = mgr.repo.set_repeats(ds["id"], h, 3)
    assert ok

    row = mgr.repo.conn.execute(
        "SELECT repeats FROM dataset_images WHERE dataset_id = ? AND media_hash = ?",
        (ds["id"], h)
    ).fetchone()
    assert row["repeats"] == 3


def test_legacy_import(manager):
    """Import old-style library: {category, value} tags → flat 'category:value' strings."""
    mgr, library_dir = manager

    # Build a fake old-style library structure
    old_lib = library_dir / "old_library" / "images"
    old_lib.mkdir(parents=True)

    make_test_image(old_lib / "aabbccdd11223344.jpeg", "green")
    import json
    (old_lib / "aabbccdd11223344.json").write_text(json.dumps({
        "name": "test_image",
        "caption": "a green square",
        "tags": [
            {"category": "class", "value": "square"},
            {"category": "color", "value": "green"},
            {"category": "meta", "value": "imported: 2025-01-01"},
        ],
        "related": {}
    }))

    # Also add a new-style flat tag JSON to make sure it's handled too
    make_test_image(old_lib / "9900aabb11223344.png", "blue")
    (old_lib / "9900aabb11223344.json").write_text(json.dumps({
        "name": "flat_image",
        "captions": {"default": "a blue square"},
        "tags": ["shape:square", "color:blue"],
    }))

    result = mgr.import_legacy_folder(str(old_lib))
    assert result["added"] == 2
    assert result["skipped"] == 0
    assert result["errors"] == 0

    page = mgr.get_page(offset=0, limit=10)
    hashes = {item["hash"] for item in page["items"]}

    # Verify old-style tags converted to flat strings
    old_img = next(item for item in page["items"] if item["hash"] == "aabbccdd11223344")
    old_data = mgr.load_image_data(old_img["hash"])
    assert "class:square" in old_data["tags"]
    assert "color:green" in old_data["tags"]
    assert old_data["captions"].get("default") == "a green square"

    # Verify new-style flat tags pass through unchanged
    new_img = next(item for item in page["items"] if item["hash"] == "9900aabb11223344")
    new_data = mgr.load_image_data(new_img["hash"])
    assert "shape:square" in new_data["tags"]
    assert new_data["captions"].get("default") == "a blue square"

    # Second import should skip both (dedup)
    result2 = mgr.import_legacy_folder(str(old_lib))
    assert result2["added"] == 0
    assert result2["skipped"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
