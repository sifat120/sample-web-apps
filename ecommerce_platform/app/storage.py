"""
storage.py — Object storage client (MinIO locally, AWS S3 in production)

Object storage is used to store product images. We do NOT store binary
files in PostgreSQL because:
  - It bloats database backups
  - It consumes database connection pool capacity for file serving
  - It prevents using a CDN for global delivery

Instead, files are uploaded to MinIO/S3 and the database stores only
the file path (a short string). Files are served directly from storage.

Local vs. production:
  The only difference is one config variable — STORAGE_ENDPOINT_URL.
  Set it to "http://localhost:9000" for MinIO, or leave it unset for AWS S3.
  No code changes are needed when deploying to production.
"""

import boto3
from botocore.exceptions import ClientError

from app.config import settings


# Singleton S3 client — created once and reused
_s3 = None


def get_s3():
    """
    Return the shared S3/MinIO client, creating it if needed.

    boto3 is the AWS SDK for Python. It works with both real AWS S3 and
    MinIO because MinIO implements the same S3 API.

    When storage_endpoint_url is set (local development), boto3 sends
    requests to that URL instead of AWS. When it is None (production),
    boto3 automatically uses the real AWS S3 endpoints.
    """
    global _s3

    if _s3 is not None:
        return _s3

    # Build the connection arguments as a dictionary so we can
    # conditionally add endpoint_url only for local development.
    connection_args = {
        "region_name":          settings.storage_region,
        "aws_access_key_id":    settings.storage_access_key,
        "aws_secret_access_key": settings.storage_secret_key,
    }

    if settings.storage_endpoint_url:
        # Local MinIO: redirect boto3 to localhost instead of AWS
        connection_args["endpoint_url"] = settings.storage_endpoint_url

    _s3 = boto3.client("s3", **connection_args)
    return _s3


def ensure_bucket() -> None:
    """
    Create the storage bucket if it does not already exist.

    In production, the S3 bucket would be pre-created via infrastructure
    scripts (e.g. Terraform). Locally, we create it automatically on
    startup so there is no manual setup required.
    """
    s3 = get_s3()

    try:
        # head_bucket checks if the bucket exists without listing its contents.
        # It raises ClientError if the bucket does not exist or is inaccessible.
        s3.head_bucket(Bucket=settings.storage_bucket)
    except ClientError:
        # Bucket does not exist — create it
        s3.create_bucket(Bucket=settings.storage_bucket)


def upload_file(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """
    Upload a file to storage and return the storage key (path).

    Args:
        key:          The path inside the bucket, e.g. "products/7/photo.jpg"
        data:         The raw file bytes to upload
        content_type: MIME type of the file, e.g. "image/jpeg"

    Returns:
        The storage key, which is saved in the database as the file reference.
    """
    s3 = get_s3()

    s3.put_object(
        Bucket=settings.storage_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )

    return key


def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    """
    Generate a temporary, pre-signed download URL for a stored file.

    A pre-signed URL embeds a cryptographic signature that grants
    time-limited read access to a specific file — without exposing
    the storage credentials to the client.

    The client can use this URL to download the file directly from
    MinIO/S3, bypassing the API server entirely (more efficient).

    Args:
        key:        The storage path of the file (as saved in the database)
        expires_in: How many seconds until the URL expires (default 1 hour)

    Returns:
        A URL string. After expires_in seconds, the URL returns HTTP 403.
    """
    s3 = get_s3()

    presigned_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.storage_bucket, "Key": key},
        ExpiresIn=expires_in,
    )

    return presigned_url
