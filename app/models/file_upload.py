from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class FileType(str, Enum):
    EXCEL = "excel"
    PDF = "pdf"


class FileUploadRecord(BaseModel):
    batch_id: str
    original_filename: str
    saved_path: str
    file_type: FileType
    file_size_bytes: int
    rows_extracted: int = 0
    status: str = "pending"        # pending | processing | done | failed
    error_message: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class FileUploadResponse(BaseModel):
    batch_id: str
    files: list[dict]
    total_rows_extracted: int
    message: str