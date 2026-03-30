"""
Integration tests for the SQLite-backed library workflow.
"""
import pytest
from pathlib import Path
import tempfile
from PIL import Image

from src.web_app_manager import WebAppManager
from src.utils import parse_export_template, apply_export_template


def make_test_image(path: Path, color: str = "red"):
    img = Image.new("RGB", (64, 64), color=color)
    img.save(path)


@pytest.fixture
def library_dir(tmp_path):
    """Provide a temp directory for a fresh library."""
    return tmp_path


@pytest.fixture
def manager(library_dir):
    """Create and open a WebAppManager with a fresh library."""
    m = WebAppManager()
    assert m.create_new_library("Test Library", str(library_dir))
    return m


# ---------------------------------------------------------------------------
# Library creation
# ---------------------------------------------------------------------------

def test_create_library(library_dir):
    m = WebAppManager()
    ok = m.create_new_library("My Library", str(library_dir))
    assert ok
    assert m.is_open
    info = m.get_library_info()
    assert info is not None
    assert info["name"] == "My Library"
    assert info["count"] == 0


def test_load_library(library_dir):
    m1 = WebAppManager()
    m1.create_new_library("Saved Library", str(library_dir))

    # Open again from disk
    m2 = WebAppManager()
    ok = m2.load_library(library_dir)
    assert ok
    assert m2.is_open


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def test_import_images(manager, library_dir):
    # Create a folder with images
    src = library_dir / "source"
    src.mkdir()
    make_test_image(src / "a.png", "red")
    make_test_image(src / "b.png", "blue")

    result = manager.import_from_folder(str(src), recursive=False)
    assert result["added"] == 2
    assert result["skipped"] == 0

    info = manager.get_library_info()
    assert info["count"] == 2


def test_import_with_txt_sidecar(manager, library_dir):
    src = library_dir / "with_txt"
    src.mkdir()
    make_test_image(src / "img.png", "green")
    (src / "img.txt").write_text("solo, blue_hair, outdoors")

    manager.import_from_folder(str(src))

    page = manager.get_page(offset=0, limit=10)
    assert page["total"] == 1

    img_data = manager.load_image_data(page["items"][0]["hash"])
    assert "solo" in img_data["tags"]
    assert "blue_hair" in img_data["tags"]
    assert "outdoors" in img_data["tags"]


def test_import_deduplication(manager, library_dir):
    src = library_dir / "dupes"
    src.mkdir()
    make_test_image(src / "img.png", "red")

    r1 = manager.import_from_folder(str(src))
    r2 = manager.import_from_folder(str(src))
    assert r1["added"] == 1
    assert r2["added"] == 0
    assert r2["skipped"] == 1


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def test_add_and_remove_tags(manager, library_dir):
    src = library_dir / "imgs"
    src.mkdir()
    make_test_image(src / "img.png", "red")
    manager.import_from_folder(str(src))

    page = manager.get_page(offset=0, limit=10)
    h = page["items"][0]["hash"]

    manager.repo.add_tag(h, "solo")
    manager.repo.add_tag(h, "blue_hair")

    data = manager.load_image_data(h)
    assert "solo" in data["tags"]
    assert "blue_hair" in data["tags"]

    manager.repo.remove_tag(h, "solo")
    data = manager.load_image_data(h)
    assert "solo" not in data["tags"]
    assert "blue_hair" in data["tags"]


def test_set_tags(manager, library_dir):
    src = library_dir / "imgs"
    src.mkdir()
    make_test_image(src / "img.png", "red")
    manager.import_from_folder(str(src))

    page = manager.get_page(offset=0, limit=10)
    h = page["items"][0]["hash"]

    manager.repo.set_tags(h, ["1girl", "solo", "smiling"])
    data = manager.load_image_data(h)
    assert set(data["tags"]) == {"1girl", "solo", "smiling"}


# ---------------------------------------------------------------------------
# Captions
# ---------------------------------------------------------------------------

def test_save_and_load_caption(manager, library_dir):
    src = library_dir / "imgs"
    src.mkdir()
    make_test_image(src / "img.png", "red")
    manager.import_from_folder(str(src))

    page = manager.get_page(offset=0, limit=10)
    h = page["items"][0]["hash"]

    manager.save_caption(h, "1girl, solo, blue hair", "default")
    data = manager.load_image_data(h)
    assert data["captions"]["default"] == "1girl, solo, blue hair"


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

def test_filter_by_tag(manager, library_dir):
    src = library_dir / "imgs"
    src.mkdir()
    make_test_image(src / "a.png", "red")
    make_test_image(src / "b.png", "blue")
    manager.import_from_folder(str(src))

    page = manager.get_page(offset=0, limit=10)
    hashes = [item["hash"] for item in page["items"]]

    manager.repo.add_tag(hashes[0], "solo")
    manager.repo.add_tag(hashes[1], "duo")

    manager.set_filter("solo")
    filtered = manager.get_page(offset=0, limit=10)
    assert filtered["total"] == 1

    manager.clear_filter()
    all_images = manager.get_page(offset=0, limit=10)
    assert all_images["total"] == 2


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

def test_create_and_use_dataset(manager, library_dir):
    src = library_dir / "imgs"
    src.mkdir()
    make_test_image(src / "a.png", "red")
    make_test_image(src / "b.png", "blue")
    make_test_image(src / "c.png", "green")
    manager.import_from_folder(str(src))

    assert manager.create_dataset("my-dataset")

    page = manager.get_page(offset=0, limit=10)
    hashes = [item["hash"] for item in page["items"]]

    assert manager.load_dataset("my-dataset")

    added = manager.add_images_to_dataset(hashes[:2])
    assert added == 2

    ds_page = manager.get_page(offset=0, limit=10)
    assert ds_page["total"] == 2


def test_dataset_remove_images(manager, library_dir):
    src = library_dir / "imgs"
    src.mkdir()
    make_test_image(src / "a.png", "red")
    make_test_image(src / "b.png", "blue")
    manager.import_from_folder(str(src))

    # Get hashes in library mode (before loading dataset)
    lib_page = manager.get_page(offset=0, limit=10)
    hashes = [item["hash"] for item in lib_page["items"]]
    assert len(hashes) == 2

    manager.create_dataset("test-ds")
    manager.load_dataset("test-ds")

    manager.add_images_to_dataset(hashes)
    assert manager.get_page(offset=0, limit=10)["total"] == 2

    manager.remove_images_from_dataset(hashes[:1])
    assert manager.get_page(offset=0, limit=10)["total"] == 1


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

def test_taxonomy_assign(manager, library_dir):
    src = library_dir / "imgs"
    src.mkdir()
    make_test_image(src / "img.png", "red")
    manager.import_from_folder(str(src))

    page = manager.get_page(offset=0, limit=10)
    h = page["items"][0]["hash"]
    manager.repo.add_tag(h, "1girl")
    manager.repo.add_tag(h, "outdoors")

    cat_id = manager.repo.upsert_category("character", 0, "#3b82f6")
    manager.repo.set_tag_category("1girl", cat_id)

    taxonomy = manager.repo.get_taxonomy_map()
    assert taxonomy.get("1girl") == "character"
    assert taxonomy.get("outdoors") is None


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_pagination(manager, library_dir):
    src = library_dir / "imgs"
    src.mkdir()
    for i in range(5):
        make_test_image(src / f"img{i}.png", ["red", "blue", "green", "yellow", "purple"][i])
    manager.import_from_folder(str(src))

    page1 = manager.get_page(offset=0, limit=2)
    assert len(page1["items"]) == 2
    assert page1["total"] == 5
    assert page1["has_more"] is True

    page2 = manager.get_page(offset=2, limit=2)
    assert len(page2["items"]) == 2
    assert page2["has_more"] is True

    page3 = manager.get_page(offset=4, limit=2)
    assert len(page3["items"]) == 1
    assert page3["has_more"] is False

    # All hashes should be unique
    all_hashes = (
        [i["hash"] for i in page1["items"]]
        + [i["hash"] for i in page2["items"]]
        + [i["hash"] for i in page3["items"]]
    )
    assert len(set(all_hashes)) == 5


# ---------------------------------------------------------------------------
# Filter parser SQL emission
# ---------------------------------------------------------------------------

def test_filter_sql_and():
    from src.filter_parser import parse_filter, filter_node_to_sql
    node = parse_filter("solo AND blue_hair")
    sql, params = filter_node_to_sql(node)
    assert "EXISTS" in sql
    assert "solo" in params or any("solo" in str(p) for p in params)


def test_filter_sql_not():
    from src.filter_parser import parse_filter, filter_node_to_sql
    node = parse_filter("solo AND NOT duo")
    sql, params = filter_node_to_sql(node)
    assert "NOT EXISTS" in sql or "NOT" in sql


def test_filter_sql_wildcard():
    from src.filter_parser import parse_filter, filter_node_to_sql
    node = parse_filter("blue*")
    sql, params = filter_node_to_sql(node)
    assert "LIKE" in sql
    assert any("blue%" in str(p) for p in params)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
