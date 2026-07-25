# import os
# import uuid
# import logging
# from datetime import datetime
# from fastapi import APIRouter, UploadFile, File, HTTPException, Form
# from typing import Optional

# from app.core.config import settings
# from app.core.database import get_db
# from app.models.item import UploadResponse
# from app.services.excel_parser import parse_excel
# from app.services.pdf_parser import parse_pdf
# from app.services.openai_service import extract_items_with_ai
# from app.services.combiner import combine_and_prepare

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


# @router.post("/", response_model=UploadResponse)
# async def upload_files(
#     excel_file: UploadFile = File(None, description="Excel file (.xlsx or .xls)"),
#     pdf_file: UploadFile = File(None, description="PDF file (.pdf)"),
# ):
#     """
#     Upload Excel and/or PDF files.
#     AI extracts all procurement data and saves to MongoDB.
#     """
#     # Check at least one file uploaded
#     excel_provided = excel_file and excel_file.filename
#     pdf_provided = pdf_file and pdf_file.filename

#     if not excel_provided and not pdf_provided:
#         raise HTTPException(status_code=400, detail="Please upload at least one file (Excel or PDF).")

#     batch_id = str(uuid.uuid4())
#     all_raw_rows = []

#     # ── Parse Excel ──────────────────────────────────────────────
#     if excel_provided:
#         ext = os.path.splitext(excel_file.filename)[1].lower()
#         if ext not in ALLOWED_EXCEL:
#             raise HTTPException(status_code=400, detail=f"Invalid Excel file. Allowed: .xlsx, .xls")
#         path = await save_upload(excel_file, settings.UPLOAD_DIR)
#         try:
#             rows = parse_excel(path)
#             all_raw_rows.extend(rows)
#             logger.info(f"Excel rows extracted: {len(rows)}")
#         except Exception as e:
#             raise HTTPException(status_code=422, detail=f"Excel parse failed: {str(e)}")

#     # ── Parse PDF ────────────────────────────────────────────────
#     if pdf_provided:
#         ext = os.path.splitext(pdf_file.filename)[1].lower()
#         if ext not in ALLOWED_PDF:
#             raise HTTPException(status_code=400, detail=f"Invalid PDF file. Allowed: .pdf")
#         path = await save_upload(pdf_file, settings.UPLOAD_DIR)
#         try:
#             rows = parse_pdf(path)
#             all_raw_rows.extend(rows)
#             logger.info(f"PDF rows extracted: {len(rows)}")
#         except Exception as e:
#             raise HTTPException(status_code=422, detail=f"PDF parse failed: {str(e)}")

#     if not all_raw_rows:
#         raise HTTPException(status_code=422, detail="No data could be extracted from the uploaded files.")

#     # ── AI Extraction ─────────────────────────────────────────────
#     try:
#         ai_items = await extract_items_with_ai(all_raw_rows)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"AI extraction failed: {str(e)}")

#     # ── Combine + Determine Status ────────────────────────────────
#     prepared_items = combine_and_prepare(ai_items, source_label="combined")

#     if not prepared_items:
#         raise HTTPException(status_code=422, detail="AI could not extract any structured items.")

#     # ── Save to MongoDB ───────────────────────────────────────────
#     db = get_db()
#     now = datetime.utcnow()
#     docs = []
#     for item in prepared_items:
#         item["batch_id"] = batch_id
#         item["created_at"] = now
#         item["updated_at"] = now
#         docs.append(item)

#     await db["items"].insert_many(docs)

#     parsed_count = sum(1 for d in docs if d["status"] == "Parsed")
#     needs_review_count = sum(1 for d in docs if d["status"] == "Needs Review")

#     return UploadResponse(
#         batch_id=batch_id,
#         total_items=len(docs),
#         parsed=parsed_count,
#         needs_review=needs_review_count,
#         message=f"✅ {len(docs)} items extracted and saved. {needs_review_count} need review."
#     )


# @router.get("/batch/{batch_id}")
# async def get_batch_status(batch_id: str):
#     """Get all items from a specific upload batch."""
#     db = get_db()
#     items = await db["items"].find({"batch_id": batch_id}).to_list(length=None)
#     for item in items:
#         item["_id"] = str(item["_id"])
#     return {"batch_id": batch_id, "total": len(items), "items": items}

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
from app.models.file_upload import FileUploadHistoryItem, FileUploadRecord, FileType
from app.models.item import UploadResponse
from app.services.excel_parser import parse_excel
from app.services.pdf_parser import parse_pdf
from app.services.text_parser import parse_text
from app.services.openai_service import extract_items_with_ai
from app.services.combiner import combine_and_prepare
from app.services.image_parser import extract_items_from_image
from app.services.s3_service import upload_to_s3

try:
    from app.services.pptx_parser import parse_pptx
except RuntimeError as exc:
    parse_pptx = None
    logging.getLogger(__name__).warning(
        "pptx parser is unavailable: %s", exc
    )

try:
    from app.services.docx_parser import parse_docx
except RuntimeError as exc:
    parse_docx = None
    logging.getLogger(__name__).warning(
        "docx parser is unavailable: %s", exc
    )


router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_EXCEL = {".xlsx", ".xls"}
ALLOWED_PDF = {".pdf"}
ALLOWED_IMAGE = {".png", ".jpg", ".jpeg"}
ALLOWED_DOCX = {".docx"}
ALLOWED_PPTX = {".pptx"}
ALLOWED_TEXT = {".txt"}


async def save_upload(file: UploadFile, upload_dir: str) -> tuple[str, int]:
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1].lower()
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(upload_dir, unique_name)
    content = await file.read()

    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large. Max {settings.MAX_FILE_SIZE_MB}MB.")

    with open(file_path, "wb") as f:
        f.write(content)
    return file_path, len(content)


async def save_and_record_upload(
    file: UploadFile,
    upload_dir: str,
    db,
    batch_id: str,
    project_id: str,
    file_type: FileType,
) -> tuple[str, str, int]:
    file_path, file_size_bytes = await save_upload(file, upload_dir)
    filename = os.path.basename(file_path.replace('\\', '/'))
    try:
        s3_url = upload_to_s3(file_path, filename)
    except Exception as e:
        logger.error(f"S3 upload failed for {filename}: {e}")
        s3_url = f"/api/uploads/{filename}"

    record = FileUploadRecord(
        batch_id=batch_id,
        project_id=project_id,
        original_filename=file.filename,
        saved_path=file_path,
        file_type=file_type,
        file_size_bytes=file_size_bytes,
        status="uploaded",
        download_url=s3_url,
    )
    await db["uploaded_files"].insert_one(record.dict())
    return file_path, s3_url, file_size_bytes


async def process_file_list(
    files: list[UploadFile],
    allowed_exts: set[str],
    parser,
    file_type: FileType,
    file_type_name: str,
    db,
    batch_id: str,
    project_id: str,
    uploaded_files_list: list[dict],
    all_raw_rows: list,
) -> None:
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_exts:
            raise HTTPException(status_code=400, detail=f"Invalid {file_type_name} file. Allowed: {', '.join(sorted(allowed_exts))}")
        path, s3_url, _ = await save_and_record_upload(file, settings.UPLOAD_DIR, db, batch_id, project_id, file_type)
        uploaded_files_list.append({
            "original_filename": file.filename,
            "download_url": s3_url,
            "file_type": file_type_name,
        })
        try:
            rows = parser(path)
            all_raw_rows.extend(rows)
            logger.info(f"{file_type_name.upper()} rows extracted: {len(rows)}")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"{file_type_name.upper()} parse failed: {str(e)}")


@router.get("/history", response_model=list[FileUploadHistoryItem])
async def get_upload_history(
    project_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    file_type: Optional[FileType] = None,
    limit: Optional[int] = 100,
):
    """Return upload history with saved file links."""
    db = get_db()
    query = {}
    if project_id:
        query["project_id"] = project_id
    if batch_id:
        query["batch_id"] = batch_id
    if file_type:
        query["file_type"] = file_type.value

    records = await db["uploaded_files"].find(query).sort("uploaded_at", -1).to_list(length=limit)
    history = []
    for record in records:
        saved_path = record["saved_path"]
        filename = os.path.basename(saved_path.replace('\\', '/'))
        download_url = record.get("download_url") or f"/api/uploads/{filename}"
        history.append({
            "id": str(record["_id"]),
            "batch_id": record["batch_id"],
            "project_id": record.get("project_id"),
            "original_filename": record["original_filename"],
            "saved_path": saved_path,
            "file_type": record["file_type"],
            "file_size_bytes": record["file_size_bytes"],
            "rows_extracted": record.get("rows_extracted", 0),
            "status": record.get("status", "pending"),
            "error_message": record.get("error_message"),
            "uploaded_at": record["uploaded_at"],
            "download_url": download_url,
        })
    return history


@router.post("/", response_model=UploadResponse)
async def upload_files(
    project_id: str = Form(..., description="Project ID to associate items with"),
    excel_file: List[OptionalUploadFile] = File(default=[], description="Excel files (.xlsx or .xls)"),
    pdf_file: List[OptionalUploadFile] = File(default=[], description="PDF files (.pdf)"),
    docx_file: List[OptionalUploadFile] = File(default=[], description="Word files (.docx)"),
    pptx_file: List[OptionalUploadFile] = File(default=[], description="PowerPoint files (.pptx)"),
    txt_file: List[OptionalUploadFile] = File(default=[], description="Text files (.txt)"),
    image_file: List[OptionalUploadFile] = File(default=[], description="Image files (.png, .jpg, .jpeg)"),
):
    """
    Upload Excel, PDF, DOCX, PPTX, TXT, and/or Image files with a project ID.
    AI extracts all procurement data and saves to MongoDB.
    """
    excel_files = [f for f in (excel_file or []) if f and hasattr(f, "filename") and f.filename]
    pdf_files = [f for f in (pdf_file or []) if f and hasattr(f, "filename") and f.filename]
    docx_files = [f for f in (docx_file or []) if f and hasattr(f, "filename") and f.filename]
    pptx_files = [f for f in (pptx_file or []) if f and hasattr(f, "filename") and f.filename]
    txt_files = [f for f in (txt_file or []) if f and hasattr(f, "filename") and f.filename]
    image_files = [f for f in (image_file or []) if f and hasattr(f, "filename") and f.filename]

    if not any([excel_files, pdf_files, docx_files, pptx_files, txt_files, image_files]):
        raise HTTPException(status_code=400, detail="Please upload at least one file (Excel, PDF, DOCX, PPTX, TXT, or Image).")

    batch_id = str(uuid.uuid4())
    db = get_db()
    all_raw_rows = []
    image_items = []
    uploaded_files_list = []

    # ── Parse Excel ──────────────────────────────────────────────
    if excel_files:
        await process_file_list(
            excel_files,
            ALLOWED_EXCEL,
            parse_excel,
            FileType.EXCEL,
            "excel",
            db,
            batch_id,
            project_id,
            uploaded_files_list,
            all_raw_rows,
        )

    # ── Parse PDF ──────────────────────────────────────────────
    if pdf_files:
        await process_file_list(
            pdf_files,
            ALLOWED_PDF,
            parse_pdf,
            FileType.PDF,
            "pdf",
            db,
            batch_id,
            project_id,
            uploaded_files_list,
            all_raw_rows,
        )

    # ── Parse DOCX ──────────────────────────────────────────────
    if docx_files:
        if parse_docx is None:
            raise HTTPException(
                status_code=500,
                detail="DOCX support is unavailable because python-docx is not installed."
            )
        await process_file_list(
            docx_files,
            ALLOWED_DOCX,
            parse_docx,
            FileType.DOCX,
            "docx",
            db,
            batch_id,
            project_id,
            uploaded_files_list,
            all_raw_rows,
        )

    # ── Parse PPTX ──────────────────────────────────────────────
    if pptx_files:
        if parse_pptx is None:
            raise HTTPException(
                status_code=500,
                detail="PPTX support is unavailable because python-pptx is not installed."
            )
        await process_file_list(
            pptx_files,
            ALLOWED_PPTX,
            parse_pptx,
            FileType.PPTX,
            "pptx",
            db,
            batch_id,
            project_id,
            uploaded_files_list,
            all_raw_rows,
        )

    # ── Parse TXT ──────────────────────────────────────────────
    if txt_files:
        await process_file_list(
            txt_files,
            ALLOWED_TEXT,
            parse_text,
            FileType.TXT,
            "txt",
            db,
            batch_id,
            project_id,
            uploaded_files_list,
            all_raw_rows,
        )

    if not all_raw_rows and not image_files:
        raise HTTPException(status_code=422, detail="No data could be extracted from the uploaded files.")

    # ── AI Extraction for Excel/PDF ──────────────────────────────────────
    try:
        if all_raw_rows:
            ai_items = await extract_items_with_ai(all_raw_rows)
        else:
            ai_items = []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {str(e)}")

    # ── Parse Image ──────────────────────────────────────────────
    if image_files:
        for image in image_files:
            ext = os.path.splitext(image.filename)[1].lower()
            if ext not in ALLOWED_IMAGE:
                raise HTTPException(status_code=400, detail="Invalid Image file. Allowed: .png, .jpg, .jpeg")
            path, s3_url, _ = await save_and_record_upload(image, settings.UPLOAD_DIR, db, batch_id, project_id, FileType.IMAGE)
            uploaded_files_list.append({
                "original_filename": image.filename,
                "download_url": s3_url,
                "file_type": "image"
            })
            try:
                image_extracted = await extract_items_from_image(path)
                image_items.extend(image_extracted)
                logger.info(f"Image items extracted: {len(image_extracted)}")
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"Image parse failed: {str(e)}")

    # Merge results
    ai_items.extend(image_items)

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
        item["project_id"] = project_id
        item["created_at"] = now
        item["updated_at"] = now
        # ✅ Fix: convert enum to string so MongoDB saves correctly
        item["status"] = item["status"].value if hasattr(item["status"], "value") else item["status"]
        item["missing_fields"] = item.get("missing_fields", [])
        docs.append(item)

    await db["items"].insert_many(docs)

    parsed_count = sum(1 for d in docs if d["status"] == "Parsed")
    needs_review_count = sum(1 for d in docs if d["status"] == "Needs Review")

    # ── Serialize docs for response (convert non-JSON-safe types) ──
    response_items = []
    for d in docs:
        item_dict = {k: v for k, v in d.items() if k not in ("_id", "raw_data")}
        # Convert datetime to string
        for key in ("created_at", "updated_at"):
            if key in item_dict and hasattr(item_dict[key], "isoformat"):
                item_dict[key] = item_dict[key].isoformat()
        response_items.append(item_dict)

    return UploadResponse(
        batch_id=batch_id,
        project_id=project_id,
        total_items=len(docs),
        parsed=parsed_count,
        needs_review=needs_review_count,
        message=f"Extracted {len(docs)} items. {parsed_count} parsed, {needs_review_count} need review.",
        files=uploaded_files_list,
        items=response_items,
    )


@router.get("/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """Get all items from a specific upload batch."""
    db = get_db()
    items = await db["items"].find({"batch_id": batch_id}).to_list(length=None)
    for item in items:
        item["_id"] = str(item["_id"])
    return {"batch_id": batch_id, "total": len(items), "items": items}
