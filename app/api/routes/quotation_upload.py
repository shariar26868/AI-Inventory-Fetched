import os
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional

from app.core.config import settings
from app.core.database import get_db
from app.models.quotation import QuotationUploadResponse
from app.services.excel_parser import parse_excel
from app.services.pdf_parser import parse_pdf
from app.services.quotation_openai_service import extract_quotations_with_ai, determine_quotation_status

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


async def ensure_no_bad_indexes():
    """Drop any unique index on quotation_number to allow null values."""
    db = get_db()
    try:
        indexes = await db["quotations"].index_information()
        for index_name, index_info in indexes.items():
            if index_name == "_id_":
                continue
            key_fields = [k for k, _ in index_info.get("key", [])]
            if "number" in key_fields or "quotation_number" in key_fields:
                await db["quotations"].drop_index(index_name)
                logger.info(f"Dropped problematic index: {index_name}")
    except Exception as e:
        logger.warning(f"Index cleanup warning: {e}")


@router.post("/", response_model=QuotationUploadResponse)
async def upload_quotation(
    project_id: str = Form(..., description="Project ID to associate quotations with"),
    excel_file: UploadFile = File(None, description="Excel file (.xlsx or .xls)"),
    pdf_file: UploadFile = File(None, description="PDF file (.pdf)"),
):
    """
    Upload Excel and/or PDF quotation files.
    AI extracts quotation data including header info + line items and saves to MongoDB.
    """
    excel_provided = excel_file and excel_file.filename
    pdf_provided = pdf_file and pdf_file.filename

    if not excel_provided and not pdf_provided:
        raise HTTPException(status_code=400, detail="Please upload at least one file (Excel or PDF).")

    # Drop bad unique indexes before insert
    await ensure_no_bad_indexes()

    batch_id = str(uuid.uuid4())
    all_raw_rows = []

    # ── Parse Excel ──────────────────────────────────────────────
    if excel_provided:
        ext = os.path.splitext(excel_file.filename)[1].lower()
        if ext not in ALLOWED_EXCEL:
            raise HTTPException(status_code=400, detail="Invalid Excel file. Allowed: .xlsx, .xls")
        path = await save_upload(excel_file, settings.UPLOAD_DIR)
        try:
            rows = parse_excel(path)
            all_raw_rows.extend(rows)
            logger.info(f"Quotation Excel rows: {len(rows)}")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Excel parse failed: {str(e)}")

    # ── Parse PDF ────────────────────────────────────────────────
    if pdf_provided:
        ext = os.path.splitext(pdf_file.filename)[1].lower()
        if ext not in ALLOWED_PDF:
            raise HTTPException(status_code=400, detail="Invalid PDF file. Allowed: .pdf")
        path = await save_upload(pdf_file, settings.UPLOAD_DIR)
        try:
            rows = parse_pdf(path)
            all_raw_rows.extend(rows)
            logger.info(f"Quotation PDF rows: {len(rows)}")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"PDF parse failed: {str(e)}")

    if not all_raw_rows:
        raise HTTPException(status_code=422, detail="No data could be extracted from the uploaded files.")

    # ── AI Extraction ─────────────────────────────────────────────
    try:
        ai_quotations = await extract_quotations_with_ai(all_raw_rows)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {str(e)}")

    if not ai_quotations:
        raise HTTPException(status_code=422, detail="AI could not extract any quotations.")

    # ── Prepare + Save to MongoDB ─────────────────────────────────
    db = get_db()
    now = datetime.utcnow()
    docs = []

    for q in ai_quotations:
        if not q:
            continue

        status, missing = determine_quotation_status(q)

        # Normalize items list
        items = q.get("items") or []
        normalized_items = []
        for item in items:
            normalized_items.append({
                "item_name": item.get("item_name"),
                "quantity": item.get("quantity"),
                "unit_price": item.get("unit_price"),
                "total": item.get("total"),
                "remarks": item.get("remarks"),
                "item_type": item.get("item_type"),
            })

        doc = {
            "quotation_number": q.get("quotation_number") or f"QT-{uuid.uuid4().hex[:8].upper()}",  # fallback ID if null
            "project_id": project_id,
            "project_name": q.get("project_name"),
            "supplier": q.get("supplier"),
            "total_amount": q.get("total_amount"),
            "currency": q.get("currency"),
            "valid_until": q.get("valid_until"),
            "payment_terms": q.get("payment_terms"),
            "delivery_terms": q.get("delivery_terms"),
            "items": normalized_items,
            "status": status,
            "missing_fields": missing,
            "batch_id": batch_id,
            "source_file": "excel" if excel_provided else "pdf",
            "raw_data": {},         # skip raw_data to keep docs small
            "created_at": now,
            "updated_at": now,
        }
        docs.append(doc)

    # Insert one by one to avoid full batch failure
    inserted = 0
    for doc in docs:
        try:
            await db["quotations"].insert_one(doc)
            inserted += 1
        except Exception as e:
            logger.error(f"Failed to insert quotation {doc.get('quotation_number')}: {e}")

    if inserted == 0:
        raise HTTPException(status_code=500, detail="Failed to save any quotations to database.")

    parsed_count = sum(1 for d in docs if d["status"] == "Parsed")
    needs_review_count = sum(1 for d in docs if d["status"] == "Needs Review")

    return QuotationUploadResponse(
        batch_id=batch_id,
        project_id=project_id,
        total_quotations=inserted,
        parsed=parsed_count,
        needs_review=needs_review_count,
        message=f"✅ {inserted} quotations extracted and saved. {needs_review_count} need review."
    )


@router.get("/batch/{batch_id}")
async def get_quotation_batch(batch_id: str):
    """Get all quotations from a specific upload batch."""
    db = get_db()
    quotations = await db["quotations"].find({"batch_id": batch_id}).to_list(length=None)
    for q in quotations:
        q["_id"] = str(q["_id"])
    return {"batch_id": batch_id, "total": len(quotations), "quotations": quotations}


@router.get("/project/{project_id}")
async def get_quotations_by_project(project_id: str):
    """Get all quotations for a specific project."""
    db = get_db()
    quotations = await db["quotations"].find({"project_id": project_id}).to_list(length=None)
    for q in quotations:
        q["_id"] = str(q["_id"])
    return {"project_id": project_id, "total": len(quotations), "quotations": quotations}


@router.get("/{quotation_id}")
async def get_quotation_detail(quotation_id: str):
    """Get a single quotation with all its items."""
    from bson import ObjectId
    db = get_db()
    if not ObjectId.is_valid(quotation_id):
        raise HTTPException(status_code=400, detail="Invalid quotation ID")
    q = await db["quotations"].find_one({"_id": ObjectId(quotation_id)})
    if not q:
        raise HTTPException(status_code=404, detail="Quotation not found")
    q["_id"] = str(q["_id"])
    return q