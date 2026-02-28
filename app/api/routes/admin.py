from fastapi import APIRouter, HTTPException
from bson import ObjectId
from datetime import datetime

from app.core.database import get_db
from app.models.item import AdminStatusUpdate, ItemStatus

router = APIRouter()


def serialize(item: dict) -> dict:
    item["_id"] = str(item["_id"])
    return item


# Status transition rules
ALLOWED_TRANSITIONS = {
    ItemStatus.PARSED: [ItemStatus.NEEDS_REVIEW, ItemStatus.LOCKED],
    ItemStatus.NEEDS_REVIEW: [ItemStatus.PARSED, ItemStatus.LOCKED],
    ItemStatus.LOCKED: [ItemStatus.APPROVED, ItemStatus.NEEDS_REVIEW],
    ItemStatus.APPROVED: [ItemStatus.LOCKED],  # admin can revert if needed
}


@router.patch("/status/{item_id}")
async def update_item_status(item_id: str, body: AdminStatusUpdate):
    """
    Admin changes item status.
    Flow: Parsed → Needs Review → Locked → Approved
    Admin can also revert backward.
    """
    db = get_db()
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid item ID")

    item = await db["items"].find_one({"_id": ObjectId(item_id)})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    current_status = ItemStatus(item["status"])
    new_status = body.status

    allowed = ALLOWED_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{current_status}' to '{new_status}'. "
                   f"Allowed: {[s.value for s in allowed]}"
        )

    update = {
        "status": new_status,
        "updated_at": datetime.utcnow(),
    }
    if body.note:
        update["admin_note"] = body.note

    await db["items"].update_one({"_id": ObjectId(item_id)}, {"$set": update})

    updated = await db["items"].find_one({"_id": ObjectId(item_id)})
    return {
        "message": f"Status updated: {current_status} → {new_status}",
        "item": serialize(updated)
    }


@router.patch("/bulk-status")
async def bulk_update_status(batch_id: str, body: AdminStatusUpdate):
    """
    Admin updates status for all items in a batch at once.
    """
    db = get_db()
    result = await db["items"].update_many(
        {"batch_id": batch_id},
        {"$set": {"status": body.status, "updated_at": datetime.utcnow()}}
    )
    return {
        "message": f"Updated {result.modified_count} items to '{body.status}'",
        "modified": result.modified_count
    }


@router.get("/needs-review")
async def get_needs_review(page: int = 1, limit: int = 20):
    """Get all items that need admin review."""
    db = get_db()
    skip = (page - 1) * limit
    total = await db["items"].count_documents({"status": ItemStatus.NEEDS_REVIEW})
    items = await db["items"].find({"status": ItemStatus.NEEDS_REVIEW}).skip(skip).limit(limit).to_list(length=limit)
    return {
        "total": total,
        "items": [serialize(i) for i in items]
    }