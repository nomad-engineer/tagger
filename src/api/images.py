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
async def get_thumbnail(image_hash: str):
    """Serve a cached thumbnail or fall back to full image."""
    if not app_manager.is_open:
        raise HTTPException(status_code=404, detail="No library loaded")

    thumb = app_manager.get_thumbnail_path(image_hash)
    if thumb and thumb.exists():
        return FileResponse(thumb, headers={"Cache-Control": "max-age=3600"})

    # Fallback: serve full image
    source = app_manager.repo.get_media_file_path(image_hash)
    if source:
        return FileResponse(source)

    raise HTTPException(status_code=404, detail=f"Image {image_hash} not found")


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
