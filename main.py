# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from app.api.routes import upload, items, admin
# from app.core.database import connect_db, close_db

# app = FastAPI(
#     title="Procurement AI API",
#     description="AI-powered procurement data extraction from Excel & PDF",
#     version="1.0.0"
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
# app.include_router(items.router, prefix="/api/items", tags=["Items"])
# app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])


# @app.on_event("startup")
# async def startup():
#     await connect_db()


# @app.on_event("shutdown")
# async def shutdown():
#     await close_db()


# @app.get("/")
# async def root():
#     return {"message": "Procurement AI API is running ✅"}




import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.routes import upload, items, admin
from app.api.routes import quotation_upload          # ← নতুন line
from app.core.config import settings
from app.core.database import connect_db, close_db

app = FastAPI(
    title="Procurement AI API",
    description="AI-powered procurement data extraction from Excel & PDF",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=os.path.abspath(settings.UPLOAD_DIR)), name="uploads")

app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(items.router, prefix="/api/items", tags=["Items"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(quotation_upload.router, prefix="/api/quotations", tags=["Quotations"])  # ← নতুন line


@app.on_event("startup")
async def startup():
    await connect_db()


@app.on_event("shutdown")
async def shutdown():
    await close_db()


@app.get("/")
async def root():
    return {"message": "Procurement AI API is running ✅"}