from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from src.main import app_manager
from src.commands import BatchAddTagsCommand, BatchRemoveTagsCommand, FindReplaceCommand, DeduplicateTagsCommand

router = APIRouter(prefix="/api/tags", tags=["tags"])


class BatchTagRequest(BaseModel):
    value: str
    hashes: List[str]


class SetTagsRequest(BaseModel):
    hashes: List[str]
    tags: List[str]


@router.get("/suggestions")
async def get_tag_suggestions(q: str = ""):
    """Get tag suggestions for autocomplete."""
    return {"suggestions": app_manager.get_tag_suggestions(q)}


@router.get("/counts")
async def get_tag_counts():
    """Get all tags with counts in the current view."""
    return {"tags": app_manager.get_all_tags_with_counts()}


@router.post("/batch-add")
async def batch_add_tags(req: BatchTagRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    cmd = BatchAddTagsCommand(app_manager, req.hashes, req.value)
    app_manager.command_manager.execute_command(cmd)
    return {"status": "success", "applied": len(cmd.applied_hashes)}


@router.post("/batch-remove")
async def batch_remove_tags(req: BatchTagRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    cmd = BatchRemoveTagsCommand(app_manager, req.hashes, req.value)
    app_manager.command_manager.execute_command(cmd)
    return {"status": "success", "removed": len(cmd.removed_from_hashes)}


class BatchRemoveMultiRequest(BaseModel):
    values: List[str]
    hashes: List[str]


@router.post("/batch-remove-multi")
async def batch_remove_multi_tags(req: BatchRemoveMultiRequest):
    """Remove multiple tag values from multiple images in one call."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    total_removed = 0
    for value in req.values:
        cmd = BatchRemoveTagsCommand(app_manager, req.hashes, value)
        app_manager.command_manager.execute_command(cmd)
        total_removed += len(cmd.removed_from_hashes)
    return {"status": "success", "removed": total_removed}


class ReorderTagsRequest(BaseModel):
    hash: str
    tags: List[str]


@router.post("/reorder")
async def reorder_tags(req: ReorderTagsRequest):
    """Set the full ordered tag list for an image (reorder / edit)."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    success = app_manager.repo.set_tags(req.hash, req.tags)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to reorder tags")
    return {"status": "success"}


class BatchRenameTagRequest(BaseModel):
    old_value: str
    new_value: str
    hashes: List[str]


@router.post("/batch-rename")
async def batch_rename_tag(req: BatchRenameTagRequest):
    """Rename a tag only on images that have it. Does not add to images missing the old tag."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    repo = app_manager.repo
    renamed = 0
    for h in req.hashes:
        rows = repo.conn.execute(
            "SELECT value FROM tags WHERE media_hash = ? ORDER BY position", (h,)
        ).fetchall()
        tags = [r[0] for r in rows]
        if req.old_value in tags:
            new_tags = [req.new_value if t == req.old_value else t for t in tags]
            repo.set_tags(h, new_tags)
            renamed += 1
    return {"status": "success", "renamed": renamed}


class GlobalRenameTagRequest(BaseModel):
    old_value: str
    new_value: str


@router.post("/global-rename")
async def global_rename_tag(req: GlobalRenameTagRequest):
    """
    Rename a tag across ALL images that have it, and migrate its taxonomy
    (category) assignment so the category binding follows the rename.

    Also works for pre-declared taxonomy tags that aren't applied to any
    image yet (count=0) — in that case only the taxonomy row is updated.
    """
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    old = req.old_value.strip()
    new = req.new_value.strip()
    if not old or not new or old == new:
        return {"status": "noop", "renamed": 0, "taxonomy_updated": False}
    repo = app_manager.repo

    # Rename on all images that have the old tag
    rows = repo.conn.execute(
        "SELECT DISTINCT media_hash FROM tags WHERE value = ?", (old,)
    ).fetchall()
    renamed = 0
    for row in rows:
        h = row[0]
        tag_rows = repo.conn.execute(
            "SELECT value FROM tags WHERE media_hash = ? ORDER BY position", (h,)
        ).fetchall()
        tags = [r[0] for r in tag_rows]
        new_tags = [new if t == old else t for t in tags]
        repo.set_tags(h, new_tags)
        renamed += 1

    # Migrate taxonomy (category) assignment from old → new value
    taxonomy_updated = False
    tax_row = repo.conn.execute(
        "SELECT category_id FROM tag_taxonomy WHERE tag_value = ?", (old,)
    ).fetchone()
    if tax_row is not None:
        cat_id = tax_row[0]
        repo.conn.execute(
            "DELETE FROM tag_taxonomy WHERE tag_value = ?", (old,)
        )
        repo.conn.execute("""
            INSERT INTO tag_taxonomy (tag_value, category_id) VALUES (?, ?)
            ON CONFLICT(tag_value) DO UPDATE SET category_id = excluded.category_id
        """, (new, cat_id))
        repo.conn.commit()
        taxonomy_updated = True

    return {
        "status": "success",
        "renamed": renamed,
        "taxonomy_updated": taxonomy_updated,
    }


class GlobalDeleteTagsRequest(BaseModel):
    values: List[str]


@router.post("/global-delete")
async def global_delete_tags(req: GlobalDeleteTagsRequest):
    """Delete tags from ALL images that have them."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    repo = app_manager.repo
    total_removed = 0
    for value in req.values:
        rows = repo.conn.execute(
            "SELECT DISTINCT media_hash FROM tags WHERE value = ?", (value,)
        ).fetchall()
        for row in rows:
            h = row[0]
            repo.remove_tag(h, value)
            total_removed += 1
    return {"status": "success", "removed": total_removed}


class FindReplaceRequest(BaseModel):
    search: str
    replace: str
    in_tags: bool = True
    in_captions: bool = False
    scope: str = "library"  # "library", "dataset", "selection"
    selected_hashes: Optional[List[str]] = None


class FindReplacePreviewRequest(BaseModel):
    search: str
    in_tags: bool = True
    in_captions: bool = False
    scope: str = "library"
    selected_hashes: Optional[List[str]] = None


@router.post("/find-replace/preview")
async def find_replace_preview(req: FindReplacePreviewRequest):
    """Preview how many items would be affected by a find-and-replace."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    if not req.search:
        return {"tag_matches": 0, "caption_matches": 0}

    repo = app_manager.repo
    hashes = _get_scoped_hashes(req.scope, req.selected_hashes)

    tag_matches = 0
    caption_matches = 0

    if req.in_tags:
        for h in hashes:
            rows = repo.conn.execute(
                "SELECT value FROM tags WHERE media_hash = ?", (h,)
            ).fetchall()
            for r in rows:
                if req.search in r[0]:
                    tag_matches += 1

    if req.in_captions:
        for h in hashes:
            rows = repo.conn.execute(
                "SELECT content FROM captions WHERE media_hash = ?", (h,)
            ).fetchall()
            for r in rows:
                if req.search in r[0]:
                    caption_matches += 1

    return {"tag_matches": tag_matches, "caption_matches": caption_matches}


@router.post("/find-replace")
async def find_replace(req: FindReplaceRequest):
    """Find and replace text in tags and/or captions. Undoable via Ctrl+Z."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    if not req.search:
        raise HTTPException(status_code=400, detail="Search text is required")
    if not (req.in_tags or req.in_captions):
        raise HTTPException(status_code=400, detail="Must search in tags or captions")

    hashes = _get_scoped_hashes(req.scope, req.selected_hashes)
    cmd = FindReplaceCommand(
        app_manager,
        hashes,
        req.search,
        req.replace,
        req.in_tags,
        req.in_captions,
    )
    app_manager.command_manager.execute_command(cmd)

    return {
        "status": "success",
        "tags_replaced": cmd.tag_values_replaced,
        "captions_replaced": len(cmd.caption_changes),
    }


def _get_scoped_hashes(scope: str, selected_hashes: Optional[List[str]] = None) -> List[str]:
    """Get image hashes based on scope."""
    repo = app_manager.repo
    if scope == "selection" and selected_hashes:
        return selected_hashes
    elif scope == "dataset" and app_manager.current_dataset_id is not None:
        rows = repo.conn.execute(
            "SELECT media_hash FROM dataset_images WHERE dataset_id = ?",
            (app_manager.current_dataset_id,)
        ).fetchall()
        return [r[0] for r in rows]
    else:
        # Library-wide
        rows = repo.conn.execute("SELECT hash FROM media").fetchall()
        return [r[0] for r in rows]


@router.get("/find-duplicates")
async def find_duplicate_tags():
    """Scan the library for images that have duplicate tags."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    repo = app_manager.repo
    rows = repo.conn.execute("""
        SELECT media_hash, value, COUNT(*) as cnt
        FROM tags
        GROUP BY media_hash, value
        HAVING cnt > 1
    """).fetchall()

    # Group by image hash
    images: dict = {}
    for r in rows:
        h = r[0]
        if h not in images:
            # Get the image name for display
            name_row = repo.conn.execute(
                "SELECT name FROM media WHERE hash = ?", (h,)
            ).fetchone()
            images[h] = {
                "hash": h,
                "name": name_row[0] if name_row else h[:12],
                "duplicates": [],
            }
        images[h]["duplicates"].append({
            "tag": r[1],
            "count": r[2],
        })

    return {
        "images": list(images.values()),
        "total_images": len(images),
        "total_duplicates": sum(r[2] - 1 for r in rows),
    }


class DeduplicateRequest(BaseModel):
    hashes: Optional[List[str]] = None  # None = all affected images


@router.post("/deduplicate")
async def deduplicate_tags(req: DeduplicateRequest):
    """Remove duplicate tags from images. Undoable via Ctrl+Z."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    repo = app_manager.repo

    if req.hashes:
        target_hashes = req.hashes
    else:
        # Find all images with duplicate tags
        rows = repo.conn.execute("""
            SELECT DISTINCT media_hash
            FROM tags
            GROUP BY media_hash, value
            HAVING COUNT(*) > 1
        """).fetchall()
        target_hashes = [r[0] for r in rows]

    if not target_hashes:
        return {"status": "noop", "images_fixed": 0, "duplicates_removed": 0}

    cmd = DeduplicateTagsCommand(app_manager, target_hashes)
    app_manager.command_manager.execute_command(cmd)

    return {
        "status": "success",
        "images_fixed": len(cmd.changes),
        "duplicates_removed": cmd.duplicates_removed,
    }


@router.post("/undo")
async def undo():
    success = app_manager.command_manager.undo()
    if not success:
        raise HTTPException(status_code=400, detail="Nothing to undo")
    return {"status": "success"}


@router.post("/redo")
async def redo():
    success = app_manager.command_manager.redo()
    if not success:
        raise HTTPException(status_code=400, detail="Nothing to redo")
    return {"status": "success"}
