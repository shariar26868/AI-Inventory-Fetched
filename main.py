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

from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="Procurement AI API",
    description="AI-powered procurement data extraction from Excel & PDF",
    version="1.0.0"
)

def custom_openapi():
    app.openapi_schema = None
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["openapi"] = "3.0.2"

    def clean_properties(props):
        for prop_name, prop_val in list(props.items()):
            if prop_name.endswith("_file") and isinstance(prop_val, dict):
                props[prop_name] = {
                    "type": "array",
                    "items": {"type": "string", "format": "binary"},
                    "title": prop_val.get("title", prop_name),
                    "description": prop_val.get("description", ""),
                    "default": []
                }

    schemas = openapi_schema.get("components", {}).get("schemas", {})
    for schema_name, schema_def in schemas.items():
        if "properties" in schema_def:
            clean_properties(schema_def["properties"])

    for path_item in openapi_schema.get("paths", {}).values():
        if isinstance(path_item, dict):
            for method_item in path_item.values():
                if isinstance(method_item, dict) and "requestBody" in method_item:
                    content = method_item["requestBody"].get("content", {})
                    for media_type, media_def in content.items():
                        if "schema" in media_def and "properties" in media_def["schema"]:
                            clean_properties(media_def["schema"]["properties"])

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

@app.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint():
    return custom_openapi()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=os.path.abspath(settings.UPLOAD_DIR)), name="uploads")
app.mount("/api/uploads", StaticFiles(directory=os.path.abspath(settings.UPLOAD_DIR)), name="api_uploads")


app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(items.router, prefix="/api/items", tags=["Items"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(quotation_upload.router, prefix="/api/quotations", tags=["Quotations"])


@app.on_event("startup")
async def startup():
    await connect_db()


@app.on_event("shutdown")
async def shutdown():
    await close_db()


@app.get("/")
async def root():
    return {"message": "Procurement AI API is running ✅"}