from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class FileType(str, Enum):
    EXCEL = "excel"
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    TXT = "txt"
    IMAGE = "image"


class FileUploadRecord(BaseModel):
    batch_id: str
    project_id: Optional[str] = None
    original_filename: str
    saved_path: str
    file_type: FileType
    file_size_bytes: int
    rows_extracted: int = 0
    status: str = "pending"        # pending | uploaded | processing | done | failed
    error_message: Optional[str] = None
    download_url: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class FileUploadHistoryItem(BaseModel):
    id: str
    batch_id: str
    project_id: Optional[str] = None
    original_filename: str
    saved_path: str
    file_type: FileType
    file_size_bytes: int
    rows_extracted: int = 0
    status: str = "pending"
    error_message: Optional[str] = None
    uploaded_at: datetime
    download_url: str


class FileUploadResponse(BaseModel):
    batch_id: str
    files: list[dict]
    total_rows_extracted: int
    message: str