from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from src.main import app_manager
from src.commands import BatchAddTagsCommand, BatchRemoveTagsCommand

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
