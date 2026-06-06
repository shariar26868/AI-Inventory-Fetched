import boto3
import logging
import os
from botocore.exceptions import NoCredentialsError, ClientError
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )


def upload_to_s3(file_path: str, filename: str) -> str:
    """
    Uploads a file to the S3 bucket and returns its public URL.
    """
    s3_client = get_s3_client()
    bucket_name = settings.AWS_S3_BUCKET_NAME

    try:
        logger.info(f"Uploading file {file_path} to S3 bucket {bucket_name} as {filename}...")
        s3_client.upload_file(
            file_path,
            bucket_name,
            filename
        )
        
        region = settings.AWS_REGION
        if region == "us-east-1":
            url = f"https://{bucket_name}.s3.amazonaws.com/{filename}"
        else:
            url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{filename}"
        
        logger.info(f"Successfully uploaded {filename} to S3 bucket {bucket_name}. URL: {url}")
        return url
    except FileNotFoundError:
        logger.error(f"Local file not found: {file_path}")
        raise
    except NoCredentialsError:
        logger.error("AWS credentials not available or invalid")
        raise
    except ClientError as e:
        logger.error(f"Failed to upload to S3 client error: {e}")
        raise
