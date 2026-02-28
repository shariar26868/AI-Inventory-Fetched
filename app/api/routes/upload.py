import os
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional

from app.core.config import settings
from app.core.database import get_db
from app.models.item import UploadResponse
from app.services.excel_parser import parse_excel
from app.services.pdf_parser import parse_pdf
from app.services.openai_service import extract_items_with_ai
from app.services.combiner import combine_and_prepare

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_EXCEL = {".xlsx", ".xls"}
ALLOWED_PDF = {".pdf"}


async def save_upload(file: UploadFile, upload_dir: str) -> str:
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1].lower()
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(upload_dir, unique_name)
    content = await file.read()

    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large. Max {settings.MAX_FILE_SIZE_MB}MB.")

    with open(file_path, "wb") as f:
        f.write(content)
    return file_path


@router.post("/", response_model=UploadResponse)
async def upload_files(
    excel_file: UploadFile = File(None, description="Excel file (.xlsx or .xls)"),
    pdf_file: UploadFile = File(None, description="PDF file (.pdf)"),
):
    """
    Upload Excel and/or PDF files.
    AI extracts all procurement data and saves to MongoDB.
    """
    # Check at least one file uploaded
    excel_provided = excel_file and excel_file.filename
    pdf_provided = pdf_file and pdf_file.filename

    if not excel_provided and not pdf_provided:
        raise HTTPException(status_code=400, detail="Please upload at least one file (Excel or PDF).")

    batch_id = str(uuid.uuid4())
    all_raw_rows = []

    # ── Parse Excel ──────────────────────────────────────────────
    if excel_provided:
        ext = os.path.splitext(excel_file.filename)[1].lower()
        if ext not in ALLOWED_EXCEL:
            raise HTTPException(status_code=400, detail=f"Invalid Excel file. Allowed: .xlsx, .xls")
        path = await save_upload(excel_file, settings.UPLOAD_DIR)
        try:
            rows = parse_excel(path)
            all_raw_rows.extend(rows)
            logger.info(f"Excel rows extracted: {len(rows)}")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Excel parse failed: {str(e)}")

    # ── Parse PDF ────────────────────────────────────────────────
    if pdf_provided:
        ext = os.path.splitext(pdf_file.filename)[1].lower()
        if ext not in ALLOWED_PDF:
            raise HTTPException(status_code=400, detail=f"Invalid PDF file. Allowed: .pdf")
        path = await save_upload(pdf_file, settings.UPLOAD_DIR)
        try:
            rows = parse_pdf(path)
            all_raw_rows.extend(rows)
            logger.info(f"PDF rows extracted: {len(rows)}")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"PDF parse failed: {str(e)}")

    if not all_raw_rows:
        raise HTTPException(status_code=422, detail="No data could be extracted from the uploaded files.")

    # ── AI Extraction ─────────────────────────────────────────────
    try:
        ai_items = await extract_items_with_ai(all_raw_rows)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {str(e)}")

    # ── Combine + Determine Status ────────────────────────────────
    prepared_items = combine_and_prepare(ai_items, source_label="combined")

    if not prepared_items:
        raise HTTPException(status_code=422, detail="AI could not extract any structured items.")

    # ── Save to MongoDB ───────────────────────────────────────────
    db = get_db()
    now = datetime.utcnow()
    docs = []
    for item in prepared_items:
        item["batch_id"] = batch_id
        item["created_at"] = now
        item["updated_at"] = now
        docs.append(item)

    await db["items"].insert_many(docs)

    parsed_count = sum(1 for d in docs if d["status"] == "Parsed")
    needs_review_count = sum(1 for d in docs if d["status"] == "Needs Review")

    return UploadResponse(
        batch_id=batch_id,
        total_items=len(docs),
        parsed=parsed_count,
        needs_review=needs_review_count,
        message=f"✅ {len(docs)} items extracted and saved. {needs_review_count} need review."
    )


@router.get("/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """Get all items from a specific upload batch."""
    db = get_db()
    items = await db["items"].find({"batch_id": batch_id}).to_list(length=None)
    for item in items:
        item["_id"] = str(item["_id"])
    return {"batch_id": batch_id, "total": len(items), "items": items}