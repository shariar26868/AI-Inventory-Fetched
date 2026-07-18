import boto3
import logging
import os
from botocore.exceptions import NoCredentialsError, ClientError
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_s3_client():
    session_kwargs = {
        "region_name": settings.AWS_REGION,
    }

    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        session_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        session_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
        logger.info("Using explicit AWS credentials from settings for S3 client.")
    elif settings.AWS_ACCESS_KEY_ID or settings.AWS_SECRET_ACCESS_KEY:
        logger.warning(
            "Incomplete AWS credentials configured in settings. Falling back to boto3's default credential chain."
        )

    session = boto3.Session(**session_kwargs)
    credentials = session.get_credentials()
    if credentials:
        frozen = credentials.get_frozen_credentials()
        if not frozen.access_key or not frozen.secret_key:
            logger.error(
                "AWS credentials are present but incomplete: access key or secret key is blank."
            )
            raise NoCredentialsError(
                "AWS credentials are incomplete or blank. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY."
            )
        logger.info("AWS credentials loaded for S3 client. Using region %s.", settings.AWS_REGION)
    else:
        logger.error("No AWS credentials found in environment or default credential chain.")
        raise NoCredentialsError("AWS credentials are missing. Please configure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.")

    return session.client("s3")


def generate_presigned_url(s3_client, bucket_name: str, object_name: str, expiration: int = 3600) -> str:
    try:
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": object_name},
            ExpiresIn=expiration,
        )
    except ClientError as e:
        logger.error(f"Failed to generate presigned URL for {object_name}: {e}")
        raise


def upload_to_s3(file_path: str, filename: str) -> str:
    """
    Uploads a file to the S3 bucket and returns its public URL.
    """
    s3_client = get_s3_client()
    bucket_name = settings.AWS_S3_BUCKET_NAME

    try:
        logger.info(f"Uploading file {file_path} to S3 bucket {bucket_name} as {filename}...")
        
        # Upload with public-read ACL if AWS_S3_PUBLIC_ACCESS is enabled
        extra_args = {}
        if settings.AWS_S3_PUBLIC_ACCESS:
            extra_args['ACL'] = 'public-read'
        
        s3_client.upload_file(
            file_path,
            bucket_name,
            filename,
            ExtraArgs=extra_args
        )

        # Use presigned URL only if not using public access and presigned URLs are enabled
        if not settings.AWS_S3_PUBLIC_ACCESS and settings.AWS_S3_USE_PRESIGNED_URL:
            presigned_url = generate_presigned_url(
                s3_client,
                bucket_name,
                filename,
                expiration=settings.AWS_S3_PRESIGNED_URL_EXPIRES_IN,
            )
            logger.info(
                "Successfully uploaded %s and generated presigned URL for S3 bucket %s.",
                filename,
                bucket_name,
            )
            return presigned_url

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
