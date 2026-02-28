# Procurement AI API

AI-powered procurement data extraction from Excel & PDF files using FastAPI + OpenAI + MongoDB.

## Folder Structure

```
procurement-ai/
├── main.py                        ← FastAPI entry point (ROOT)
├── requirements.txt
├── .env
├── .gitignore
├── uploads/                       ← Temp uploaded files
└── app/
    ├── api/
    │   └── routes/
    │       ├── upload.py          ← POST /api/upload/
    │       ├── items.py           ← GET/PATCH/DELETE /api/items/
    │       └── admin.py           ← PATCH /api/admin/status/{id}
    ├── core/
    │   ├── config.py              ← Settings from .env
    │   └── database.py            ← MongoDB Motor connection
    ├── models/
    │   └── item.py                ← Pydantic models + ItemStatus enum
    ├── services/
    │   ├── excel_parser.py        ← Parse .xlsx/.xls files
    │   ├── pdf_parser.py          ← Parse .pdf files (tables + text)
    │   ├── openai_service.py      ← GPT-4o extraction
    │   └── combiner.py            ← Merge data + assign status
    └── utils/
        └── helpers.py
```

## Status Flow

```
File Upload
    ↓ AI Extraction
Parsed          ← all fields found
Needs Review    ← some fields missing
    ↓ Admin confirms
Locked          ← admin verified
    ↓ Client approves
Approved        ← final
```

## Setup

```bash
# 1. Clone and enter project
cd procurement-ai

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure .env
cp .env .env.local
# Edit .env → add your OPENAI_API_KEY and MONGODB_URL

# 5. Run server
uvicorn main:app --reload --port 8000
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upload/` | Upload Excel + PDF files |
| GET | `/api/upload/batch/{batch_id}` | Get items by batch |
| GET | `/api/items/` | List all items (filter by status/batch) |
| GET | `/api/items/{id}` | Get single item |
| PATCH | `/api/items/{id}` | Update item fields |
| DELETE | `/api/items/{id}` | Delete item |
| GET | `/api/items/stats/summary` | Status counts |
| PATCH | `/api/admin/status/{id}` | Admin: change status |
| PATCH | `/api/admin/bulk-status` | Admin: bulk status update |
| GET | `/api/admin/needs-review` | Admin: items needing review |

## Swagger UI

Visit: `http://localhost:8000/docs`