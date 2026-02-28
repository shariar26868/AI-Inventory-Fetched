from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from bson import ObjectId
from datetime import datetime

from app.core.database import get_db
from app.models.item import ItemUpdateModel, ItemStatus

router = APIRouter()


def serialize(item: dict) -> dict:
    item["_id"] = str(item["_id"])
    return item


@router.get("/")
async def get_all_items(
    status: Optional[ItemStatus] = Query(None, description="Filter by status"),
    batch_id: Optional[str] = Query(None, description="Filter by batch"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Get all procurement items with optional filters and pagination."""
    db = get_db()
    query = {}
    if status:
        query["status"] = status
    if batch_id:
        query["batch_id"] = batch_id

    skip = (page - 1) * limit
    total = await db["items"].count_documents(query)
    items = await db["items"].find(query).skip(skip).limit(limit).to_list(length=limit)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [serialize(i) for i in items]
    }


@router.get("/{item_id}")
async def get_item(item_id: str):
    """Get a single item by ID."""
    db = get_db()
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid item ID")

    item = await db["items"].find_one({"_id": ObjectId(item_id)})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return serialize(item)


@router.patch("/{item_id}")
async def update_item(item_id: str, data: ItemUpdateModel):
    """Update item fields."""
    db = get_db()
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid item ID")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_data["updated_at"] = datetime.utcnow()

    result = await db["items"].update_one(
        {"_id": ObjectId(item_id)},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")

    updated = await db["items"].find_one({"_id": ObjectId(item_id)})
    return serialize(updated)


@router.delete("/{item_id}")
async def delete_item(item_id: str):
    """Delete an item."""
    db = get_db()
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid item ID")

    result = await db["items"].delete_one({"_id": ObjectId(item_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")

    return {"message": "Item deleted successfully"}


@router.get("/stats/summary")
async def get_stats():
    """Get summary counts by status."""
    db = get_db()
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    results = await db["items"].aggregate(pipeline).to_list(length=None)
    stats = {r["_id"]: r["count"] for r in results}
    stats["total"] = sum(stats.values())
    return stats