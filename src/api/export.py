"""
Export API — export images + metadata for library, dataset, or selection.

Metadata can be written as .txt (comma-separated tags) or .json (full MediaData,
re-importable via legacy import).
"""

import threading
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.main import app_manager

router = APIRouter(prefix="/api/export", tags=["export"])


class ExportRequest(BaseModel):
    output_dir: str
    scope: str = "library"            # "library" | "dataset" | "selection"
    dataset_name: Optional[str] = None
    selected_hashes: Optional[List[str]] = None
    metadata_format: str = "json"     # "json" | "txt"
    copy_images: bool = True
    use_symlinks: bool = False


@router.post("")
async def export_images(req: ExportRequest):
    """Start a background export. Poll /api/export/status for progress."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")

    # Resolve which hashes to export
    if req.scope == "selection":
        if not req.selected_hashes:
            raise HTTPException(status_code=400, detail="No images selected")
        hashes = req.selected_hashes
    elif req.scope == "dataset":
        if not req.dataset_name:
            raise HTTPException(status_code=400, detail="No dataset specified")
        ds = app_manager.repo.get_dataset_by_name(req.dataset_name)
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset '{req.dataset_name}' not found")
        rows = app_manager.repo.conn.execute(
            "SELECT media_hash FROM dataset_images WHERE dataset_id = ?",
            (ds["id"],),
        ).fetchall()
        hashes = [r["media_hash"] for r in rows]
    else:
        # library — all images
        hashes = [r[0] for r in app_manager.repo.conn.execute(
            "SELECT hash FROM media ORDER BY imported_at"
        ).fetchall()]

    if not hashes:
        raise HTTPException(status_code=400, detail="Nothing to export")

    output = Path(req.output_dir)

    # Start background export
    ok = app_manager.start_export(
        hashes=hashes,
        output_dir=output,
        metadata_format=req.metadata_format,
        copy_images=req.copy_images,
        use_symlinks=req.use_symlinks,
    )
    if not ok:
        raise HTTPException(status_code=409, detail="An export or import is already running")

    return {"status": "started", "total": len(hashes)}


@router.get("/status")
async def export_status():
    """Poll export progress."""
    progress = app_manager.get_export_status()
    if progress is None:
        return {"running": False}
    return progress


@router.post("/cancel")
async def export_cancel():
    """Cancel a running export."""
    cancelled = app_manager.cancel_export()
    return {"cancelled": cancelled}
