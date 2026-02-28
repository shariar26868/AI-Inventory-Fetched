from pydantic import BaseModel, Field
from typing import Optional, List, Any
from enum import Enum
from datetime import datetime


class ItemStatus(str, Enum):
    PARSED = "Parsed"
    NEEDS_REVIEW = "Needs Review"
    LOCKED = "Locked"
    APPROVED = "Approved"


class ItemModel(BaseModel):
    item_name: Optional[str] = None
    item_code: Optional[str] = None
    description: Optional[str] = None
    qty: Optional[str] = None
    manufacturer: Optional[str] = None
    commodity: Optional[str] = None
    status: ItemStatus = ItemStatus.PARSED
    source_file: Optional[str] = None      # "excel" | "pdf" | "combined"
    batch_id: Optional[str] = None         # upload session id
    raw_data: Optional[dict] = {}          # original extracted row
    missing_fields: Optional[List[str]] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ItemUpdateModel(BaseModel):
    item_name: Optional[str] = None
    item_code: Optional[str] = None
    description: Optional[str] = None
    qty: Optional[str] = None
    manufacturer: Optional[str] = None
    commodity: Optional[str] = None


class AdminStatusUpdate(BaseModel):
    status: ItemStatus
    note: Optional[str] = None


class UploadResponse(BaseModel):
    batch_id: str
    total_items: int
    parsed: int
    needs_review: int
    message: str