from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from src.main import app_manager

router = APIRouter(prefix="/api/library", tags=["library"])


class LibraryCreateRequest(BaseModel):
    name: str
    path: str


class LibraryLoadRequest(BaseModel):
    path: str


class FilterRequest(BaseModel):
    expression: str = ""


class ImportRequest(BaseModel):
    folder_path: str
    recursive: bool = True


# -----------------------------------------------------------------------

@router.get("/current")
async def get_current_library():
    info = app_manager.get_library_info()
    if not info:
        return None
    return info


@router.post("/create-new")
async def create_new_library(req: LibraryCreateRequest):
    success = app_manager.create_new_library(req.name, req.path)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create library")
    return {"status": "success", "name": req.name, "path": req.path, "count": 0}


@router.post("/load")
async def load_library(req: LibraryLoadRequest):
    lib_path = Path(req.path)
    if not lib_path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")
    try:
        success = app_manager.load_library(lib_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not success:
        raise HTTPException(status_code=500, detail="Failed to load library")
    info = app_manager.get_library_info()
    return {"status": "success", **(info or {})}


@router.post("/filter")
async def set_filter(req: FilterRequest):
    app_manager.set_filter(req.expression)
    return {"status": "success", "expression": req.expression}


@router.post("/clear-filter")
async def clear_filter():
    app_manager.clear_filter()
    return {"status": "success"}


@router.post("/scan")
async def scan_library():
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    added = app_manager.scan_and_add_new_files()
    return {"status": "success", "added": added}


@router.post("/import")
async def import_from_folder(req: ImportRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    result = app_manager.import_from_folder(req.folder_path, req.recursive)
    return {"status": "success", **result}
