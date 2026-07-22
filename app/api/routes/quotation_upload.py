import os
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional, List, Union, Annotated
from pydantic import BeforeValidator

def validate_upload_file(v):
    if isinstance(v, UploadFile):
        return v
    if isinstance(v, str):
        return None
    return v

OptionalUploadFile = Annotated[Union[UploadFile, None], BeforeValidator(validate_upload_file)]

from app.core.config import settings
from app.core.database import get_db
from app.models.quotation import QuotationUploadResponse
from app.services.excel_parser import parse_excel
from app.services.pdf_parser import parse_pdf
from app.services.quotation_openai_service import extract_quotations_with_ai, determine_quotation_status
from app.services.image_parser import extract_quotations_from_image
from app.services.docx_parser import parse_docx
from app.services.pptx_parser import parse_pptx
from app.services.text_parser import parse_text

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_EXCEL = {".xlsx", ".xls"}
ALLOWED_PDF = {".pdf"}
ALLOWED_IMAGE = {".png", ".jpg", ".jpeg"}
ALLOWED_DOCX = {".docx"}
ALLOWED_PPTX = {".pptx"}
ALLOWED_TEXT = {".txt"}


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


async def process_file_list(
    files: List[UploadFile],
    allowed_exts: set[str],
    parser,
    file_type_name: str,
    upload_dir: str,
    all_raw_rows: list,
) -> None:
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_exts:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {file_type_name} file. Allowed: {', '.join(sorted(allowed_exts))}",
            )
        path = await save_upload(file, upload_dir)
        try:
            rows = parser(path)
            all_raw_rows.extend(rows)
            logger.info(f"Quotation {file_type_name.upper()} rows extracted: {len(rows)}")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"{file_type_name.upper()} parse failed: {str(e)}")


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
    project_id: str = Form(..., description="Project ID"),
    rfqId: Optional[str] = Form(None, description="Project / Hotel name"),
    vendorId: Optional[str] = Form(None, description="vendorId / Vendor name"),
    total_amount: Optional[str] = Form(None, description="Total amount e.g. USD 68,750"),
    currency: Optional[str] = Form(None, description="Currency e.g. USD"),
    valid_until: Optional[str] = Form(None, description="Validity date e.g. Mar 23, 2026"),
    payment_terms: Optional[str] = Form(None, description="Payment terms e.g. 40% advance"),
    delivery_terms: Optional[str] = Form(None, description="Delivery terms e.g. DDP Dubai"),
    excel_file: List[OptionalUploadFile] = File(default=[], description="Excel files (.xlsx or .xls)"),
    pdf_file: List[OptionalUploadFile] = File(default=[], description="PDF files (.pdf)"),
    docx_file: List[OptionalUploadFile] = File(default=[], description="Word files (.docx)"),
    pptx_file: List[OptionalUploadFile] = File(default=[], description="PowerPoint files (.pptx)"),
    txt_file: List[OptionalUploadFile] = File(default=[], description="Text files (.txt)"),
    image_file: List[OptionalUploadFile] = File(default=[], description="Image files (.png, .jpg, .jpeg)"),
):
    """Upload quotation files in batch and parse their line items."""
    excel_files = [f for f in (excel_file or []) if f and hasattr(f, "filename") and f.filename]
    pdf_files = [f for f in (pdf_file or []) if f and hasattr(f, "filename") and f.filename]
    docx_files = [f for f in (docx_file or []) if f and hasattr(f, "filename") and f.filename]
    pptx_files = [f for f in (pptx_file or []) if f and hasattr(f, "filename") and f.filename]
    txt_files = [f for f in (txt_file or []) if f and hasattr(f, "filename") and f.filename]
    image_files = [f for f in (image_file or []) if f and hasattr(f, "filename") and f.filename]

    if not any([excel_files, pdf_files, docx_files, pptx_files, txt_files, image_files]):
        raise HTTPException(
            status_code=400,
            detail="Please upload at least one file (Excel, PDF, DOCX, PPTX, TXT, or Image).",
        )

    await ensure_no_bad_indexes()

    batch_id = str(uuid.uuid4())
    all_raw_rows = []
    image_quotations = []

    if excel_files:
        await process_file_list(
            excel_files,
            ALLOWED_EXCEL,
            parse_excel,
            "excel",
            settings.UPLOAD_DIR,
            all_raw_rows,
        )

    if pdf_files:
        await process_file_list(
            pdf_files,
            ALLOWED_PDF,
            parse_pdf,
            "pdf",
            settings.UPLOAD_DIR,
            all_raw_rows,
        )

    if docx_files:
        await process_file_list(
            docx_files,
            ALLOWED_DOCX,
            parse_docx,
            "docx",
            settings.UPLOAD_DIR,
            all_raw_rows,
        )

    if pptx_files:
        await process_file_list(
            pptx_files,
            ALLOWED_PPTX,
            parse_pptx,
            "pptx",
            settings.UPLOAD_DIR,
            all_raw_rows,
        )

    if txt_files:
        await process_file_list(
            txt_files,
            ALLOWED_TEXT,
            parse_text,
            "txt",
            settings.UPLOAD_DIR,
            all_raw_rows,
        )

    if image_files:
        for image in image_files:
            ext = os.path.splitext(image.filename)[1].lower()
            if ext not in ALLOWED_IMAGE:
                raise HTTPException(status_code=400, detail="Invalid Image file. Allowed: .png, .jpg, .jpeg")
            path = await save_upload(image, settings.UPLOAD_DIR)
            try:
                image_extracted = await extract_quotations_from_image(path)
                image_quotations.extend(image_extracted)
                logger.info(f"Image quotations extracted: {len(image_extracted)}")
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"Image parse failed: {str(e)}")

    if not all_raw_rows and not image_quotations:
        raise HTTPException(status_code=422, detail="No data could be extracted from the uploaded files.")

    try:
        ai_quotations = await extract_quotations_with_ai(all_raw_rows) if all_raw_rows else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {str(e)}")

    ai_quotations.extend(image_quotations)

    if not ai_quotations:
        raise HTTPException(status_code=422, detail="AI could not extract any quotations.")

    all_items = []
    first_quotation_number = None

    for q in ai_quotations:
        if not q:
            continue
        if not first_quotation_number:
            first_quotation_number = q.get("quotation_number")
        for item in (q.get("items") or []):
            all_items.append(
                {
                    "item_name": item.get("item_name"),
                    "description": item.get("description"),
                    "commodity": item.get("commodity"),
                    "quantity": item.get("quantity"),
                    "unit_price": item.get("unit_price"),
                    "total": item.get("total"),
                    "remarks": item.get("remarks"),
                    "item_type": item.get("item_type"),
                }
            )

    source_file = "image" if image_files and not any([excel_files, pdf_files, docx_files, pptx_files, txt_files]) else (
        "excel" if excel_files else "pdf" if pdf_files else "docx" if docx_files else "pptx" if pptx_files else "txt"
    )

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
        "source_file": source_file,
        "raw_data": {},
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    try:
        await get_db()["quotations"].insert_one(doc)
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
        message=f"✅ 1 quotation saved with {len(all_items)} items.",
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
