from typing import Optional
from bson import ObjectId
from datetime import datetime
import logging

from app.core.database import get_db
from app.models.item import ItemStatus

logger = logging.getLogger(__name__)

# Full transition map
ALLOWED_TRANSITIONS = {
    ItemStatus.PARSED: [ItemStatus.NEEDS_REVIEW, ItemStatus.LOCKED],
    ItemStatus.NEEDS_REVIEW: [ItemStatus.PARSED, ItemStatus.LOCKED],
    ItemStatus.LOCKED: [ItemStatus.APPROVED, ItemStatus.NEEDS_REVIEW],
    ItemStatus.APPROVED: [ItemStatus.LOCKED],
}


class StatusService:

    @staticmethod
    async def change_status(
        item_id: str,
        new_status: ItemStatus,
        note: Optional[str] = None,
        force: bool = False  # admin can force any transition
    ) -> dict:
        """
        Change status of a single item.
        Validates transition rules unless force=True.
        """
        db = get_db()

        if not ObjectId.is_valid(item_id):
            raise ValueError(f"Invalid item ID: {item_id}")

        item = await db["items"].find_one({"_id": ObjectId(item_id)})
        if not item:
            raise LookupError(f"Item not found: {item_id}")

        current_status = ItemStatus(item["status"])

        if not force:
            allowed = ALLOWED_TRANSITIONS.get(current_status, [])
            if new_status not in allowed:
                raise PermissionError(
                    f"Cannot transition '{current_status}' → '{new_status}'. "
                    f"Allowed next: {[s.value for s in allowed]}"
                )

        update_payload = {
            "status": new_status.value,
            "updated_at": datetime.utcnow(),
        }
        if note:
            update_payload["status_note"] = note

        await db["items"].update_one(
            {"_id": ObjectId(item_id)},
            {"$set": update_payload}
        )

        logger.info(f"Item {item_id}: {current_status} → {new_status}")
        updated = await db["items"].find_one({"_id": ObjectId(item_id)})
        updated["_id"] = str(updated["_id"])
        return updated

    @staticmethod
    async def bulk_change_status(
        batch_id: str,
        new_status: ItemStatus,
        note: Optional[str] = None
    ) -> dict:
        """
        Change status for all items in a batch.
        No transition validation — admin bulk operation.
        """
        db = get_db()

        update_payload = {
            "status": new_status.value,
            "updated_at": datetime.utcnow(),
        }
        if note:
            update_payload["status_note"] = note

        result = await db["items"].update_many(
            {"batch_id": batch_id},
            {"$set": update_payload}
        )

        logger.info(f"Bulk status update: batch={batch_id}, status={new_status}, modified={result.modified_count}")
        return {
            "batch_id": batch_id,
            "new_status": new_status.value,
            "modified": result.modified_count
        }

    @staticmethod
    async def auto_assign_status(item: dict) -> ItemStatus:
        """
        Automatically assign status based on completeness of required fields.
        Used after AI extraction.
        """
        REQUIRED_FIELDS = ["item_name", "item_code", "description", "qty", "manufacturer", "commodity"]
        missing = [f for f in REQUIRED_FIELDS if not item.get(f)]

        if missing:
            logger.debug(f"Item missing fields: {missing} → Needs Review")
            return ItemStatus.NEEDS_REVIEW

        return ItemStatus.PARSED

    @staticmethod
    async def get_status_summary() -> dict:
        """Return count of items grouped by status."""
        db = get_db()
        pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        results = await db["items"].aggregate(pipeline).to_list(length=None)
        summary = {r["_id"]: r["count"] for r in results}
        summary["total"] = sum(summary.values())
        return summary