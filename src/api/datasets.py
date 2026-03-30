from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from src.main import app_manager

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


class DatasetCreateRequest(BaseModel):
    name: str
    description: str = ""


class DatasetLoadRequest(BaseModel):
    name: str


class DatasetImagesRequest(BaseModel):
    image_hashes: List[str]


class CaptionProfileRequest(BaseModel):
    template: str = ""
    remove_duplicates: bool = False
    max_tags: int = 0


class RepeatsRequest(BaseModel):
    media_hash: str
    repeats: int


# -----------------------------------------------------------------------

@router.get("/list")
async def list_datasets():
    if not app_manager.is_open:
        return {"datasets": []}
    return {"datasets": app_manager.repo.list_datasets()}


@router.post("/create")
async def create_dataset(req: DatasetCreateRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    success = app_manager.create_dataset(req.name, req.description)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to create dataset '{req.name}' (may already exist)")
    return {"status": "success"}


@router.post("/load")
async def load_dataset(req: DatasetLoadRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    success = app_manager.load_dataset(req.name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Dataset '{req.name}' not found")
    return {"status": "success"}


@router.post("/close")
async def close_dataset():
    app_manager.close_dataset()
    return {"status": "success"}


@router.get("/current")
async def get_current_dataset():
    if app_manager.current_dataset_id is None:
        return None
    return app_manager.repo.get_dataset(app_manager.current_dataset_id)


@router.post("/add-images")
async def add_images(req: DatasetImagesRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    added = app_manager.add_images_to_dataset(req.image_hashes)
    return {"status": "success", "added": added}


@router.post("/remove-images")
async def remove_images(req: DatasetImagesRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    removed = app_manager.remove_images_from_dataset(req.image_hashes)
    return {"status": "success", "removed": removed}


@router.get("/images")
async def get_images(offset: int = 0, limit: int = 200, sort: str = "default"):
    """Get paginated images for the current view (library or dataset)."""
    if not app_manager.is_open:
        return {"items": [], "total": 0, "offset": offset, "limit": limit, "has_more": False}
    return app_manager.get_page(offset=offset, limit=limit, sort=sort)


@router.put("/caption-profile")
async def save_caption_profile(req: CaptionProfileRequest):
    if not app_manager.is_open or app_manager.current_dataset_id is None:
        raise HTTPException(status_code=400, detail="No dataset loaded")
    success = app_manager.repo.save_caption_profile(
        app_manager.current_dataset_id,
        req.template,
        req.remove_duplicates,
        req.max_tags,
    )
    return {"status": "success" if success else "error"}


@router.put("/repeats")
async def set_repeats(req: RepeatsRequest):
    if not app_manager.is_open or app_manager.current_dataset_id is None:
        raise HTTPException(status_code=400, detail="No dataset loaded")
    success = app_manager.repo.set_repeats(
        app_manager.current_dataset_id, req.media_hash, req.repeats
    )
    return {"status": "success" if success else "error"}


@router.delete("/{dataset_name}")
async def delete_dataset(dataset_name: str):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    ds = app_manager.repo.get_dataset_by_name(dataset_name)
    if not ds:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' not found")
    if app_manager.current_dataset_id == ds["id"]:
        app_manager.close_dataset()
    success = app_manager.repo.delete_dataset(ds["id"])
    return {"status": "success" if success else "error"}
