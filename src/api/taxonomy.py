"""
Tag taxonomy API — manage library-level tag-to-category assignments.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from src.main import app_manager

router = APIRouter(prefix="/api/taxonomy", tags=["taxonomy"])


class CategoryCreateRequest(BaseModel):
    name: str
    sort_order: int = 0
    color: Optional[str] = None


class TagAssignRequest(BaseModel):
    tag_value: str
    category_id: Optional[int] = None   # None = remove assignment


class BulkAssignRequest(BaseModel):
    tag_values: List[str]
    category_id: Optional[int] = None


# -----------------------------------------------------------------------

@router.get("/categories")
async def list_categories():
    if not app_manager.is_open:
        return {"categories": []}
    return {"categories": app_manager.repo.get_categories()}


@router.post("/categories")
async def create_category(req: CategoryCreateRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    cat_id = app_manager.repo.upsert_category(req.name, req.sort_order, req.color)
    return {"status": "success", "id": cat_id}


@router.put("/categories/{category_id}")
async def update_category(category_id: int, req: CategoryCreateRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    # upsert by id — we re-use the same upsert (name as key)
    rows = app_manager.repo.conn.execute(
        "UPDATE tag_categories SET name = ?, sort_order = ?, color = ? WHERE id = ?",
        (req.name, req.sort_order, req.color, category_id),
    )
    app_manager.repo.conn.commit()
    if app_manager.repo.conn.execute("SELECT changes()").fetchone()[0] == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"status": "success"}


@router.delete("/categories/{category_id}")
async def delete_category(category_id: int):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    success = app_manager.repo.delete_category(category_id)
    return {"status": "success" if success else "error"}


@router.get("/tags")
async def list_taxonomy():
    """
    Return all unique tags in the library with their category assignment and frequency.

    Also includes tags that have been placed in the taxonomy but are not yet
    applied to any image (count = 0) — this lets users pre-populate categories.
    """
    if not app_manager.is_open:
        return {"tags": []}

    # Union of used tags (from `tags`) and pre-declared tags (from `tag_taxonomy`).
    rows = app_manager.repo.conn.execute("""
        SELECT base.value as value, base.n as n,
               tt.category_id, tc.name as category_name, tc.color
        FROM (
            SELECT value, COUNT(DISTINCT media_hash) as n
            FROM tags
            GROUP BY value
            UNION
            SELECT tag_value as value, 0 as n
            FROM tag_taxonomy
            WHERE tag_value NOT IN (SELECT DISTINCT value FROM tags)
        ) base
        LEFT JOIN tag_taxonomy tt ON tt.tag_value = base.value
        LEFT JOIN tag_categories tc ON tc.id = tt.category_id
        ORDER BY base.n DESC, base.value
    """).fetchall()

    return {
        "tags": [
            {
                "value": r["value"],
                "count": r["n"],
                "category_id": r["category_id"],
                "category_name": r["category_name"],
                "color": r["color"],
            }
            for r in rows
        ]
    }


@router.post("/assign")
async def assign_tag(req: TagAssignRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    success = app_manager.repo.set_tag_category(req.tag_value, req.category_id)
    return {"status": "success" if success else "error"}


@router.post("/assign-bulk")
async def assign_bulk(req: BulkAssignRequest):
    if not app_manager.is_open:
        raise HTTPException(status_code=400, detail="No library loaded")
    count = 0
    for tag_value in req.tag_values:
        if app_manager.repo.set_tag_category(tag_value, req.category_id):
            count += 1
    return {"status": "success", "assigned": count}
