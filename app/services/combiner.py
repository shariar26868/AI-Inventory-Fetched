from typing import List, Dict, Any
from app.models.item import ItemStatus

REQUIRED_FIELDS = ["item_name", "item_code", "description", "qty", "manufacturer", "commodity"]


def determine_status(item: Dict[str, Any]) -> tuple[ItemStatus, List[str]]:
    """
    Check which required fields are missing and assign status.
    - All fields present  → Parsed
    - Any field missing   → Needs Review
    """
    missing = [f for f in REQUIRED_FIELDS if not item.get(f)]
    if missing:
        return ItemStatus.NEEDS_REVIEW, missing
    return ItemStatus.PARSED, []


def combine_and_prepare(
    ai_items: List[Dict[str, Any]],
    source_label: str = "combined"
) -> List[Dict[str, Any]]:
    """
    Take AI-extracted items, assign status and missing_fields, return prepared list.
    """
    prepared = []

    for raw in ai_items:
        if not raw:
            continue

        status, missing = determine_status(raw)

        prepared.append({
            "item_name": raw.get("item_name"),
            "item_code": raw.get("item_code"),
            "description": raw.get("description"),
            "qty": raw.get("qty"),
            "manufacturer": raw.get("manufacturer"),
            "commodity": raw.get("commodity"),
            "status": status,
            "source_file": source_label,
            "missing_fields": missing,
            "raw_data": raw,
        })

    return prepared