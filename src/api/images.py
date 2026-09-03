from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List
from pathlib import Path

from src.main import app_manager

router = APIRouter(prefix="/api/images", tags=["images"])

IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"]
VIDEO_EXTS = [".mp4", ".avi", ".mov", ".mkv", ".webm"]
ALL_EXTS = IMAGE_EXTS + VIDEO_EXTS


@router.get("/thumbnail/{image_hash}")
async def get_thumbnail(image_hash: str, size: int = 200):
    """Serve a cached thumbnail at the requested size, or fall back to full image.

    `size` is the desired longest-edge in pixels; it is snapped up to the nearest
    cached bucket (200 / 400 / 800). The 200px preview is small and low quality
    for instant first paint; the gallery only asks for a larger tier once a cell
    is actually rendered bigger than the preview.
    """
    if not app_manager.is_open:
        raise HTTPException(status_code=404, detail="No library loaded")

    thumb = app_manager.get_thumbnail_path(image_hash, size)
    if thumb and thumb.exists():
        if size <= 200:
            # Preview tier: "no-cache" = browsers may store it but must
            # revalidate via ETag every time. FileResponse sets ETag/Last-Modified,
            # so unchanged previews get a cheap 304 while regenerated ones (e.g.
            # format/alpha changes) are picked up immediately.
            headers = {"Cache-Control": "no-cache"}
        else:
            # Larger tiers are content-addressed by hash + size and never change,
            # so they're safe to cache hard — this avoids a revalidation round
            # trip per image on every scroll.
            headers = {"Cache-Control": "public, max-age=604800, immutable"}
        return FileResponse(thumb, headers=headers)

    # Fallback: serve full image
    source = app_manager.repo.get_media_file_path(image_hash)
    if source:
        return FileResponse(source)

    raise HTTPException(status_code=404, detail=f"Image {image_hash} not found")


@router.get("/all-hashes")
async def get_all_hashes(sort: str = "default"):
    """Return all image hashes matching the current filter/dataset in sort order.

    Used by the frontend select-all so that every image is selected regardless
    of how many gallery pages have been loaded by the infinite scroll.
    """
    if not app_manager.is_open:
        raise HTTPException(status_code=404, detail="No library loaded")
    hashes = app_manager.get_all_hashes(sort=sort)
    return {"hashes": hashes}


@router.get("/data/{image_hash}")
async def get_image_data(image_hash: str):
    """Get full metadata for an image (tags, captions, related)."""
    if not app_manager.is_open:
        raise HTTPException(status_code=404, detail="No library loaded")

    data = app_manager.load_image_data(image_hash)
    if not data:
        raise HTTPException(status_code=404, detail=f"Image {image_hash} not found")
    return data


@router.get("/{image_hash}")
async def get_image(image_hash: str):
    """Serve the full-resolution image file."""
    if not app_manager.is_open:
        raise HTTPException(status_code=404, detail="No library loaded")

    source = app_manager.repo.get_media_file_path(image_hash)
    if source:
        return FileResponse(source)
    raise HTTPException(status_code=404, detail=f"Image {image_hash} not found")


class UpdateCaptionRequest(BaseModel):
    content: str
    label: str = "default"


@router.put("/caption/{image_hash}")
async def update_caption(image_hash: str, req: UpdateCaptionRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    success = app_manager.save_caption(image_hash, req.content, req.label)
    if not success:
        raise HTTPException(status_code=404, detail=f"Image {image_hash} not found")
    return {"status": "success"}


class DeleteBatchRequest(BaseModel):
    hashes: List[str]


@router.post("/delete-batch")
async def delete_images_batch(req: DeleteBatchRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    count = app_manager.delete_images_batch(req.hashes)
    return {"status": "success", "deleted": count}


class CropRequest(BaseModel):
    x: float        # percentage (0-100)
    y: float
    width: float
    height: float


@router.post("/crop/{image_hash}")
async def crop_image(image_hash: str, req: CropRequest):
    """Crop an image and create a new image from the crop."""
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")

    new_hash = app_manager.crop_image(image_hash, req.x, req.y, req.width, req.height)
    if not new_hash:
        raise HTTPException(status_code=500, detail="Crop failed")

    return {"status": "success", "hash": new_hash}
