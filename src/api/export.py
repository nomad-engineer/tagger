"""
Export API — generate .txt caption files for a dataset.
"""

import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.main import app_manager
from src.utils import parse_export_template, apply_export_template

router = APIRouter(prefix="/api/export", tags=["export"])


class ExportRequest(BaseModel):
    dataset_name: str
    output_dir: str
    use_symlinks: bool = False
    bin_by_repeats: bool = False     # Place images in sub-folders by repeat count
    copy_images: bool = True


@router.post("/dataset")
async def export_dataset(req: ExportRequest):
    """Export a dataset's images and .txt caption files to output_dir."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")

    ds = app_manager.repo.get_dataset_by_name(req.dataset_name)
    if not ds:
        raise HTTPException(status_code=404, detail=f"Dataset '{req.dataset_name}' not found")

    dataset_id = ds["id"]
    output = Path(req.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # Load caption profile
    profile_row = app_manager.repo.conn.execute(
        "SELECT template, remove_duplicates, max_tags FROM dataset_caption_profiles WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchone()
    template = profile_row["template"] if profile_row else ""
    remove_dups = bool(profile_row["remove_duplicates"]) if profile_row else False
    max_tags = profile_row["max_tags"] if profile_row else 0

    template_parts = parse_export_template(template) if template else []
    taxonomy = app_manager.repo.get_taxonomy_map()

    # Get all images in dataset with repeats
    rows = app_manager.repo.conn.execute(
        "SELECT media_hash, repeats FROM dataset_images WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchall()

    exported = 0
    errors = 0

    for row in rows:
        media_hash = row["media_hash"]
        repeats = row["repeats"]

        source_path = app_manager.repo.get_media_file_path(media_hash)
        if not source_path:
            errors += 1
            continue

        try:
            media = app_manager.repo.load_media(media_hash)
            if not media:
                errors += 1
                continue

            # Determine caption text
            if template_parts:
                caption = apply_export_template(
                    template_parts,
                    media.tags,
                    taxonomy=taxonomy,
                    remove_duplicates=remove_dups,
                    max_tags=max_tags or None,
                )
            else:
                # Use default caption or join all tags
                caption = media.get_caption("default") or ", ".join(media.tags)

            # Determine target directory
            if req.bin_by_repeats and repeats > 1:
                target_dir = output / f"{repeats}_repeats"
            else:
                target_dir = output
            target_dir.mkdir(parents=True, exist_ok=True)

            # Copy or symlink image
            dest_img = target_dir / source_path.name
            if req.copy_images:
                if not dest_img.exists():
                    shutil.copy2(source_path, dest_img)
            elif req.use_symlinks:
                if not dest_img.exists():
                    dest_img.symlink_to(source_path.resolve())

            # Write caption .txt
            txt_path = target_dir / f"{media_hash}.txt"
            txt_path.write_text(caption, encoding="utf-8")

            exported += 1
        except Exception as e:
            print(f"Error exporting {media_hash}: {e}")
            errors += 1

    return {
        "status": "success",
        "exported": exported,
        "errors": errors,
        "output_dir": str(output),
    }
