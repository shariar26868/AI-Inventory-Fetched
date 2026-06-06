from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "procurement_db"
    OPENAI_API_KEY: str = ""
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 50
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-2"
    AWS_S3_BUCKET_NAME: str = "transeas"

    class Config:
        env_file = ".env"


settings = Settings()