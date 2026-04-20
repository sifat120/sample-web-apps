"""
storage.py — Object storage client (Azurite locally, Azure Blob Storage in production)

Object storage is used to store product images. We do NOT store binary
files in PostgreSQL because:
  - It bloats database backups
  - It consumes database connection pool capacity for file serving
  - It prevents using a CDN (e.g. Azure Front Door) for global delivery

Instead, files are uploaded to Azure Blob Storage and the database
stores only the blob name (a short string). Files are served directly
from blob storage.

Local vs. production:
  The only difference is one config variable —
  AZURE_STORAGE_CONNECTION_STRING. The default points at Azurite
  (Microsoft's official Azure Blob emulator running in Docker). In
  production, set it to your real Azure storage account connection
  string. No code changes are needed when deploying.

Why Azurite?
  Azurite is the Microsoft-published emulator for the Azure Blob /
  Queue / Table APIs. The same azure-storage-blob SDK works against
  Azurite locally and against real Azure Blob Storage in production —
  identical code path, identical SAS-token download URLs.
"""

from datetime import datetime, timedelta, timezone

from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)
from azure.storage.blob._shared.base_client import parse_connection_str

from app.config import settings


# Singleton BlobServiceClient — created once and reused
_blob_service: BlobServiceClient | None = None


def get_blob_service() -> BlobServiceClient:
    """
    Return the shared BlobServiceClient, creating it if needed.

    The connection string carries the account name, account key, and
    blob endpoint. For Azurite the endpoint points at localhost:10000;
    for real Azure it points at <account>.blob.core.windows.net.
    """
    global _blob_service

    if _blob_service is None:
        _blob_service = BlobServiceClient.from_connection_string(
            settings.azure_storage_connection_string
        )

    return _blob_service


def ensure_container() -> None:
    """
    Create the blob container if it does not already exist.

    In production, the container would normally be pre-created via
    infrastructure scripts (Bicep, Terraform). Locally we create it
    automatically on startup so there is no manual setup required.
    """
    container_client = get_blob_service().get_container_client(
        settings.azure_storage_container
    )

    if not container_client.exists():
        container_client.create_container()


def upload_file(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """
    Upload a file to blob storage and return the blob name (path).

    Args:
        key:          The blob name inside the container, e.g. "products/7/photo.jpg".
                      Slashes are part of the name; Azure Blob Storage is flat
                      but the SDK and Azure Portal display them as folders.
        data:         The raw file bytes to upload
        content_type: MIME type of the file, e.g. "image/jpeg"

    Returns:
        The blob name, which is saved in the database as the file reference.
    """
    blob_client = get_blob_service().get_blob_client(
        container=settings.azure_storage_container,
        blob=key,
    )

    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )

    return key


def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    """
    Generate a temporary download URL for a stored blob, signed with a
    short-lived SAS (Shared Access Signature) token.

    A SAS URL is a cryptographically signed query string appended to the
    blob URL; it grants time-limited, operation-scoped access (here: read
    on one specific blob) without exposing the storage account key.

    The function name is kept as `generate_presigned_url` (the generic
    cross-cloud term) so call sites in the routers don't change when the
    backing technology does.

    Args:
        key:        The blob name (as saved in the database)
        expires_in: How many seconds until the URL expires (default 1 hour)

    Returns:
        A URL string. After expires_in seconds, the URL returns HTTP 403.
    """
    blob_service = get_blob_service()

    # The SAS token needs the account name and account key — both come
    # from the connection string. parse_connection_str returns
    # (primary_account_url, secondary_account_url, parsed_credential).
    _primary, _secondary, parsed_credential = parse_connection_str(
        settings.azure_storage_connection_string,
        credential=None,
        service="blob",
    )
    account_key = parsed_credential["account_key"]

    expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    sas_token = generate_blob_sas(
        account_name=blob_service.account_name,
        container_name=settings.azure_storage_container,
        blob_name=key,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=expiry,
    )

    blob_url = blob_service.get_blob_client(
        container=settings.azure_storage_container,
        blob=key,
    ).url

    return f"{blob_url}?{sas_token}"
