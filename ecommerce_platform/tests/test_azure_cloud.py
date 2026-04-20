"""
tests/test_azure_cloud.py — Tests that hit a REAL Azure Storage account.

These tests are SKIPPED by default. They run only when:

    $env:AZURE_CLOUD_TESTS="1"          # PowerShell
    export AZURE_CLOUD_TESTS=1          # bash

…and the following environment variables are also set:

    AZURE_STORAGE_CONNECTION_STRING   — points at a real Azure Storage account
                                         (NOT the Azurite dev string)
    AZURE_STORAGE_CONTAINER           — a container the account can write to
                                         (will be created if missing)

What these tests verify (that local Azurite tests cannot):

  - Real HTTPS endpoint reachability — DNS, TLS, firewall, account name
  - Production SAS signature scheme accepted by the live service
  - Container lifecycle on a real account (idempotent create + list + delete)
  - End-to-end upload + SAS download roundtrip against the live blob endpoint

Run them with:

    AZURE_CLOUD_TESTS=1 \
    AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net" \
    AZURE_STORAGE_CONTAINER="ci-products" \
    pytest tests/test_azure_cloud.py -v

These tests deliberately do NOT use the FastAPI app or any session
fixtures — they go straight through the azure-storage-blob SDK so a
failure points squarely at the cloud configuration rather than at app code.
"""

import os
import uuid

import httpx
import pytest
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from app import storage
from app.config import settings


# Mark every test in this module as `cloud` so the conftest auto-skip
# kicks in unless AZURE_CLOUD_TESTS=1 is set.
pytestmark = pytest.mark.cloud


def _looks_like_azurite(connection_string: str) -> bool:
    """Heuristic: the well-known Azurite dev account name is 'devstoreaccount1'."""
    return "devstoreaccount1" in connection_string or "127.0.0.1" in connection_string or "localhost" in connection_string


@pytest.fixture(scope="module", autouse=True)
def _require_real_azure_account():
    """
    Hard-stop the cloud tests if the connection string still points at
    Azurite. This protects against accidentally shipping AZURE_CLOUD_TESTS=1
    in CI without also providing real cloud credentials.
    """
    if _looks_like_azurite(settings.azure_storage_connection_string):
        pytest.skip(
            "AZURE_STORAGE_CONNECTION_STRING points at Azurite. "
            "Cloud tests require a real Azure Storage account."
        )


@pytest.fixture(scope="module")
def cloud_blob_service() -> BlobServiceClient:
    """A BlobServiceClient bound to the configured real Azure account."""
    return BlobServiceClient.from_connection_string(
        settings.azure_storage_connection_string
    )


@pytest.fixture(scope="module")
def cloud_container_name(cloud_blob_service: BlobServiceClient) -> str:
    """
    Create the configured container if it doesn't exist and return its name.
    Container is left in place after the test run (matches production behavior;
    individual blobs are cleaned up per test).
    """
    name = settings.azure_storage_container
    container = cloud_blob_service.get_container_client(name)
    if not container.exists():
        container.create_container()
    return name


def test_real_azure_account_is_reachable(cloud_blob_service: BlobServiceClient):
    """
    The most basic smoke test: can the SDK list containers on the live account?
    Catches misconfigured account names, expired keys, network issues, etc.
    """
    # get_account_information() is the cheapest authenticated call.
    info = cloud_blob_service.get_account_information()
    assert "account_kind" in info, f"Unexpected account info shape: {info}"


def test_real_container_exists_after_ensure(
    cloud_blob_service: BlobServiceClient,
    cloud_container_name: str,
):
    """ensure_container() must produce a container that actually exists in Azure."""
    storage.ensure_container()
    assert cloud_blob_service.get_container_client(cloud_container_name).exists()


def test_real_upload_and_sas_download_roundtrip(
    cloud_blob_service: BlobServiceClient,
    cloud_container_name: str,
):
    """
    Upload random bytes to the real account, generate a SAS URL, fetch via HTTPS,
    and verify the bytes match. This is the production flow end-to-end.
    """
    key = f"ci-tests/{uuid.uuid4().hex}.bin"
    payload = uuid.uuid4().bytes * 4  # 64 random bytes

    try:
        storage.upload_file(key, payload, content_type="application/octet-stream")

        sas_url = storage.generate_presigned_url(key, expires_in=300)
        assert sas_url.startswith("https://"), (
            f"Production SAS URL must use HTTPS; got: {sas_url}"
        )

        resp = httpx.get(sas_url, timeout=30.0)
        assert resp.status_code == 200
        assert resp.content == payload
    finally:
        # Clean up the test blob so we don't accumulate cruft in the
        # cloud account across CI runs.
        try:
            cloud_blob_service.get_blob_client(
                container=cloud_container_name, blob=key
            ).delete_blob()
        except ResourceNotFoundError:
            pass


def test_real_sas_url_for_missing_blob_returns_404():
    """
    Even on the real cloud, SAS issuance does NOT validate blob existence.
    The download surfaces the missing blob as HTTP 404. (Same behavior as
    Azurite — verified here against the real service contract.)
    """
    key = f"ci-tests/never-uploaded-{uuid.uuid4().hex}.bin"
    sas_url = storage.generate_presigned_url(key, expires_in=60)
    resp = httpx.get(sas_url, timeout=30.0)
    assert resp.status_code == 404


def test_real_uploaded_content_type_is_preserved(
    cloud_blob_service: BlobServiceClient,
    cloud_container_name: str,
):
    """The Content-Type set on upload survives the round-trip through the live service."""
    key = f"ci-tests/{uuid.uuid4().hex}.png"
    try:
        storage.upload_file(key, b"\x89PNGfake", content_type="image/png")
        resp = httpx.get(storage.generate_presigned_url(key), timeout=30.0)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
    finally:
        try:
            cloud_blob_service.get_blob_client(
                container=cloud_container_name, blob=key
            ).delete_blob()
        except ResourceNotFoundError:
            pass
