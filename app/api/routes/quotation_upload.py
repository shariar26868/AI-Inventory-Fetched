
# import os
# import uuid
# import logging
# from datetime import datetime
# from fastapi import APIRouter, UploadFile, File, HTTPException, Form
# from typing import Optional

# from app.core.config import settings
# from app.core.database import get_db
# from app.models.quotation import QuotationUploadResponse
# from app.services.excel_parser import parse_excel
# from app.services.pdf_parser import parse_pdf
# from app.services.quotation_openai_service import extract_quotations_with_ai, determine_quotation_status

# router = APIRouter()
# logger = logging.getLogger(__name__)

# ALLOWED_EXCEL = {".xlsx", ".xls"}
# ALLOWED_PDF = {".pdf"}


# async def save_upload(file: UploadFile, upload_dir: str) -> str:
#     os.makedirs(upload_dir, exist_ok=True)
#     ext = os.path.splitext(file.filename)[1].lower()
#     unique_name = f"{uuid.uuid4()}{ext}"
#     file_path = os.path.join(upload_dir, unique_name)
#     content = await file.read()

#     if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
#         raise HTTPException(status_code=413, detail=f"File too large. Max {settings.MAX_FILE_SIZE_MB}MB.")

#     with open(file_path, "wb") as f:
#         f.write(content)
#     return file_path


# async def ensure_no_bad_indexes():
#     db = get_db()
#     try:
#         indexes = await db["quotations"].index_information()
#         for index_name, index_info in indexes.items():
#             if index_name == "_id_":
#                 continue
#             key_fields = [k for k, _ in index_info.get("key", [])]
#             if "number" in key_fields or "quotation_number" in key_fields:
#                 await db["quotations"].drop_index(index_name)
#                 logger.info(f"Dropped index: {index_name}")
#     except Exception as e:
#         logger.warning(f"Index cleanup warning: {e}")


# @router.post("/", response_model=QuotationUploadResponse)
# async def upload_quotation(
#     # ── User Input Fields ─────────────────────────────────────────
#     project_id: str = Form(..., description="Project ID"),
#     rfqId: Optional[str] = Form(None, description="Project / Hotel name"),
#     vendorId: Optional[str] = Form(None, description="vendorId / Vendor name"),
#     total_amount: Optional[str] = Form(None, description="Total amount e.g. USD 68,750"),
#     currency: Optional[str] = Form(None, description="Currency e.g. USD"),
#     valid_until: Optional[str] = Form(None, description="Validity date e.g. Mar 23, 2026"),
#     payment_terms: Optional[str] = Form(None, description="Payment terms e.g. 40% advance"),
#     delivery_terms: Optional[str] = Form(None, description="Delivery terms e.g. DDP Dubai"),
#     # ── File Uploads ──────────────────────────────────────────────
#     excel_file: UploadFile = File(None, description="Excel file (.xlsx or .xls)"),
#     pdf_file: UploadFile = File(None, description="PDF file (.pdf)"),
# ):
#     """
#     Upload Excel and/or PDF quotation files.
#     Header fields (rfqId, vendorId, etc.) are taken from user input.
#     AI extracts only the line items from the file.
#     """
#     excel_provided = excel_file and excel_file.filename
#     pdf_provided = pdf_file and pdf_file.filename

#     if not excel_provided and not pdf_provided:
#         raise HTTPException(status_code=400, detail="Please upload at least one file (Excel or PDF).")

#     await ensure_no_bad_indexes()

#     batch_id = str(uuid.uuid4())
#     all_raw_rows = []

#     # ── Parse Excel ──────────────────────────────────────────────
#     if excel_provided:
#         ext = os.path.splitext(excel_file.filename)[1].lower()
#         if ext not in ALLOWED_EXCEL:
#             raise HTTPException(status_code=400, detail="Invalid Excel file. Allowed: .xlsx, .xls")
#         path = await save_upload(excel_file, settings.UPLOAD_DIR)
#         try:
#             rows = parse_excel(path)
#             all_raw_rows.extend(rows)
#             logger.info(f"Quotation Excel rows: {len(rows)}")
#         except Exception as e:
#             raise HTTPException(status_code=422, detail=f"Excel parse failed: {str(e)}")

#     # ── Parse PDF ────────────────────────────────────────────────
#     if pdf_provided:
#         ext = os.path.splitext(pdf_file.filename)[1].lower()
#         if ext not in ALLOWED_PDF:
#             raise HTTPException(status_code=400, detail="Invalid PDF file. Allowed: .pdf")
#         path = await save_upload(pdf_file, settings.UPLOAD_DIR)
#         try:
#             rows = parse_pdf(path)
#             all_raw_rows.extend(rows)
#             logger.info(f"Quotation PDF rows: {len(rows)}")
#         except Exception as e:
#             raise HTTPException(status_code=422, detail=f"PDF parse failed: {str(e)}")

#     if not all_raw_rows:
#         raise HTTPException(status_code=422, detail="No data could be extracted from the uploaded files.")

#     # ── AI Extraction (items only) ────────────────────────────────
#     try:
#         ai_quotations = await extract_quotations_with_ai(all_raw_rows)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"AI extraction failed: {str(e)}")

#     if not ai_quotations:
#         raise HTTPException(status_code=422, detail="AI could not extract any quotations.")

#     # ── Prepare + Save to MongoDB ─────────────────────────────────
#     db = get_db()
#     now = datetime.utcnow()
#     docs = []

#     for q in ai_quotations:
#         if not q:
#             continue

#         # Normalize items from AI
#         items = q.get("items") or []
#         normalized_items = []
#         for item in items:
#             normalized_items.append({
#                 "item_name": item.get("item_name"),
#                 "quantity": item.get("quantity"),
#                 "unit_price": item.get("unit_price"),
#                 "total": item.get("total"),
#                 "remarks": item.get("remarks"),
#                 "item_type": item.get("item_type"),
#             })

#         # Header fields come from user input, not AI
#         doc = {
#             "quotation_number": q.get("quotation_number") or f"QT-{uuid.uuid4().hex[:8].upper()}",
#             "project_id": project_id,
#             "rfqId": rfqId,
#             "vendorId": vendorId,
#             "total_amount": total_amount,
#             "currency": currency,
#             "valid_until": valid_until,
#             "payment_terms": payment_terms,
#             "delivery_terms": delivery_terms,
#             "items": normalized_items,
#             "status": "Parsed" if normalized_items else "Needs Review",
#             "missing_fields": [] if normalized_items else ["items"],
#             "batch_id": batch_id,
#             "source_file": "excel" if excel_provided else "pdf",
#             "raw_data": {},
#             "created_at": now,
#             "updated_at": now,
#         }
#         docs.append(doc)

#     # Insert one by one
#     inserted = 0
#     for doc in docs:
#         try:
#             await db["quotations"].insert_one(doc)
#             inserted += 1
#         except Exception as e:
#             logger.error(f"Failed to insert quotation {doc.get('quotation_number')}: {e}")

#     if inserted == 0:
#         raise HTTPException(status_code=500, detail="Failed to save any quotations to database.")

#     parsed_count = sum(1 for d in docs if d["status"] == "Parsed")
#     needs_review_count = sum(1 for d in docs if d["status"] == "Needs Review")

#     return QuotationUploadResponse(
#         batch_id=batch_id,
#         project_id=project_id,
#         rfqId=rfqId,
#         vendorId=vendorId,
#         total_amount=total_amount,
#         currency=currency,
#         valid_until=valid_until,
#         payment_terms=payment_terms,
#         delivery_terms=delivery_terms,
#         total_quotations=inserted,
#         parsed=parsed_count,
#         needs_review=needs_review_count,
#         message=f"✅ {inserted} quotations extracted and saved. {needs_review_count} need review."
#     )


# @router.get("/batch/{batch_id}")
# async def get_quotation_batch(batch_id: str):
#     db = get_db()
#     quotations = await db["quotations"].find({"batch_id": batch_id}).to_list(length=None)
#     for q in quotations:
#         q["_id"] = str(q["_id"])
#     return {"batch_id": batch_id, "total": len(quotations), "quotations": quotations}


# @router.get("/project/{project_id}")
# async def get_quotations_by_project(project_id: str):
#     db = get_db()
#     quotations = await db["quotations"].find({"project_id": project_id}).to_list(length=None)
#     for q in quotations:
#         q["_id"] = str(q["_id"])
#     return {"project_id": project_id, "total": len(quotations), "quotations": quotations}


# @router.get("/{quotation_id}")
# async def get_quotation_detail(quotation_id: str):
#     from bson import ObjectId
#     db = get_db()
#     if not ObjectId.is_valid(quotation_id):
#         raise HTTPException(status_code=400, detail="Invalid quotation ID")
#     q = await db["quotations"].find_one({"_id": ObjectId(quotation_id)})
#     if not q:
#         raise HTTPException(status_code=404, detail="Quotation not found")
#     q["_id"] = str(q["_id"])
#     return q







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
from app.services.image_parser import extract_quotations_from_image

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_EXCEL = {".xlsx", ".xls"}
ALLOWED_PDF = {".pdf"}
ALLOWED_IMAGE = {".png", ".jpg", ".jpeg"}


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
    db = get_db()
    try:
        indexes = await db["quotations"].index_information()
        for index_name, index_info in indexes.items():
            if index_name == "_id_":
                continue
            key_fields = [k for k, _ in index_info.get("key", [])]
            if "number" in key_fields or "quotation_number" in key_fields:
                await db["quotations"].drop_index(index_name)
                logger.info(f"Dropped index: {index_name}")
    except Exception as e:
        logger.warning(f"Index cleanup warning: {e}")


@router.post("/", response_model=QuotationUploadResponse)
async def upload_quotation(
    # ── User Input Fields ─────────────────────────────────────────
    project_id: str = Form(..., description="Project ID"),
    rfqId: Optional[str] = Form(None, description="Project / Hotel name"),
    vendorId: Optional[str] = Form(None, description="vendorId / Vendor name"),
    total_amount: Optional[str] = Form(None, description="Total amount e.g. USD 68,750"),
    currency: Optional[str] = Form(None, description="Currency e.g. USD"),
    valid_until: Optional[str] = Form(None, description="Validity date e.g. Mar 23, 2026"),
    payment_terms: Optional[str] = Form(None, description="Payment terms e.g. 40% advance"),
    delivery_terms: Optional[str] = Form(None, description="Delivery terms e.g. DDP Dubai"),
    # ── File Uploads ──────────────────────────────────────────────
    excel_file: UploadFile = File(None, description="Excel file (.xlsx or .xls)"),
    pdf_file: UploadFile = File(None, description="PDF file (.pdf)"),
    image_file: UploadFile = File(None, description="Image file (.png, .jpg, .jpeg)"),
):
    """
    Upload Excel and/or PDF quotation files.
    Header fields (rfqId, vendorId, etc.) are taken from user input.
    AI extracts only the line items from the file.
    One file = One vendor = One quotation (all items merged).
    """
    excel_provided = excel_file and excel_file.filename
    pdf_provided = pdf_file and pdf_file.filename
    image_provided = image_file and image_file.filename

    if not excel_provided and not pdf_provided and not image_provided:
        raise HTTPException(status_code=400, detail="Please upload at least one file (Excel, PDF, or Image).")

    await ensure_no_bad_indexes()

    batch_id = str(uuid.uuid4())
    all_raw_rows = []
    image_quotations = []

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

    if not all_raw_rows and not image_provided:
        raise HTTPException(status_code=422, detail="No data could be extracted from the uploaded files.")

    # ── AI Extraction (items only) ────────────────────────────────
    try:
        if all_raw_rows:
            ai_quotations = await extract_quotations_with_ai(all_raw_rows)
        else:
            ai_quotations = []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {str(e)}")

    # ── Parse Image ──────────────────────────────────────────────
    if image_provided:
        ext = os.path.splitext(image_file.filename)[1].lower()
        if ext not in ALLOWED_IMAGE:
            raise HTTPException(status_code=400, detail="Invalid Image file. Allowed: .png, .jpg, .jpeg")
        path = await save_upload(image_file, settings.UPLOAD_DIR)
        try:
            image_extracted = await extract_quotations_from_image(path)
            image_quotations.extend(image_extracted)
            logger.info(f"Image quotations extracted: {len(image_extracted)}")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Image parse failed: {str(e)}")
            
    # Merge results
    ai_quotations.extend(image_quotations)

    if not ai_quotations:
        raise HTTPException(status_code=422, detail="AI could not extract any quotations.")

    # ── Merge all AI results into a single quotation ──────────────
    # One file = One vendor = One quotation.
    # If AI returns multiple objects, merge all items into one doc.
    all_items = []
    first_quotation_number = None

    for q in ai_quotations:
        if not q:
            continue

        # Grab quotation_number from the first valid AI result
        if not first_quotation_number:
            first_quotation_number = q.get("quotation_number")

        for item in (q.get("items") or []):
            all_items.append({
                "item_name": item.get("item_name"),
                "description": item.get("description"),
                "commodity": item.get("commodity"),
                "quantity": item.get("quantity"),
                "unit_price": item.get("unit_price"),
                "total": item.get("total"),
                "remarks": item.get("remarks"),
                "item_type": item.get("item_type"),
            })

    # ── Prepare document ──────────────────────────────────────────
    db = get_db()
    now = datetime.utcnow()

    doc = {
        "quotation_number": first_quotation_number or f"QT-{uuid.uuid4().hex[:8].upper()}",
        "project_id": project_id,
        "rfqId": rfqId,
        "vendorId": vendorId,
        "total_amount": total_amount,
        "currency": currency,
        "valid_until": valid_until,
        "payment_terms": payment_terms,
        "delivery_terms": delivery_terms,
        "items": all_items,
        "status": "Parsed" if all_items else "Needs Review",
        "missing_fields": [] if all_items else ["items"],
        "batch_id": batch_id,
        "source_file": "image" if image_provided and not excel_provided and not pdf_provided else "excel" if excel_provided else "pdf",
        "raw_data": {},
        "created_at": now,
        "updated_at": now,
    }

    # ── Save to MongoDB ───────────────────────────────────────────
    try:
        await db["quotations"].insert_one(doc)
    except Exception as e:
        logger.error(f"Failed to insert quotation {doc.get('quotation_number')}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save quotation to database.")

    logger.info(f"Quotation saved: {doc['quotation_number']} with {len(all_items)} items.")

    return QuotationUploadResponse(
        batch_id=batch_id,
        project_id=project_id,
        rfqId=rfqId,
        vendorId=vendorId,
        total_amount=total_amount,
        currency=currency,
        valid_until=valid_until,
        payment_terms=payment_terms,
        delivery_terms=delivery_terms,
        total_quotations=1,
        parsed=1 if all_items else 0,
        needs_review=0 if all_items else 1,
        message=f"✅ 1 quotation saved with {len(all_items)} items."
    )


@router.get("/batch/{batch_id}")
async def get_quotation_batch(batch_id: str):
    db = get_db()
    quotations = await db["quotations"].find({"batch_id": batch_id}).to_list(length=None)
    for q in quotations:
        q["_id"] = str(q["_id"])
    return {"batch_id": batch_id, "total": len(quotations), "quotations": quotations}


@router.get("/project/{project_id}")
async def get_quotations_by_project(project_id: str):
    db = get_db()
    quotations = await db["quotations"].find({"project_id": project_id}).to_list(length=None)
    for q in quotations:
        q["_id"] = str(q["_id"])
    return {"project_id": project_id, "total": len(quotations), "quotations": quotations}


@router.get("/{quotation_id}")
async def get_quotation_detail(quotation_id: str):
    from bson import ObjectId
    db = get_db()
    if not ObjectId.is_valid(quotation_id):
        raise HTTPException(status_code=400, detail="Invalid quotation ID")
    q = await db["quotations"].find_one({"_id": ObjectId(quotation_id)})
    if not q:
        raise HTTPException(status_code=404, detail="Quotation not found")
    q["_id"] = str(q["_id"])
    return q