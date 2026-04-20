"""
tests/test_azure_storage.py — Edge-case coverage for the Azure Blob storage layer.

These tests exercise `app.storage` directly (no FastAPI route involved) to
pin down behaviors that are easy to regress when the SDK is upgraded or
the storage backend is swapped:

  - SAS URL parameters Azure expects (sig, se, sp, sr, sv)
  - Idempotency of ensure_container() — safe to call repeatedly
  - upload_file() overwrites blobs with the same key
  - Content-Type round-trip — the SAS download must preserve what was
    set on upload (browsers rely on this for <img>, <video>, etc.)
  - Slashes and unicode in blob names (Azure Blob is a flat namespace
    that uses '/' purely as a display convention)
  - SAS URL works for not-yet-uploaded blobs at generation time but
    yields 404 when the consumer tries to download (Azure does not
    validate existence at sign time — same as S3 pre-signed URLs)
  - Custom expiry is honored on the URL

These tests assume Azurite is running locally (the default conftest env
points at the well-known dev connection string).
"""

import asyncio
import time
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app import storage
from app.config import settings


def _unique_key(prefix: str = "tests") -> str:
    return f"{prefix}/{uuid.uuid4().hex}.bin"


def test_ensure_container_is_idempotent():
    """Calling ensure_container() multiple times must not raise."""
    storage.ensure_container()
    storage.ensure_container()
    storage.ensure_container()


def test_sas_url_includes_required_azure_query_params():
    """
    A valid Azure Blob SAS URL must include:
      sig — the HMAC signature
      se  — signed expiry timestamp
      sp  — signed permissions (we ask for read)
      sr  — signed resource type (b = single blob)
      sv  — signed Azure Storage service version
    """
    key = _unique_key()
    storage.upload_file(key, b"sas-probe", content_type="text/plain")

    url = storage.generate_presigned_url(key)
    qs = parse_qs(urlparse(url).query)

    assert "sig" in qs, f"SAS URL missing 'sig' param: {url}"
    assert "se" in qs, f"SAS URL missing expiry 'se': {url}"
    assert qs.get("sp") == ["r"], f"SAS URL must grant read-only: {qs.get('sp')}"
    assert qs.get("sr") == ["b"], f"SAS URL must scope to a single blob: {qs.get('sr')}"
    assert "sv" in qs, f"SAS URL missing service version 'sv': {url}"


def test_upload_overwrites_existing_blob():
    """
    Re-uploading to the same key must replace the existing content
    (the route uses a stable per-product key, so overwrite is required).
    """
    key = _unique_key()

    storage.upload_file(key, b"first", content_type="text/plain")
    storage.upload_file(key, b"second-much-longer-content", content_type="text/plain")

    url = storage.generate_presigned_url(key)
    resp = httpx.get(url)
    assert resp.status_code == 200
    assert resp.content == b"second-much-longer-content"


def test_uploaded_content_type_is_preserved_in_download():
    """
    The Content-Type set on upload must be the Content-Type returned by
    the SAS download. The frontend relies on this for <img src=…> tags.
    """
    key = _unique_key("image-tests")
    storage.upload_file(key, b"\xff\xd8\xff\xe0fake-jpeg", content_type="image/jpeg")

    resp = httpx.get(storage.generate_presigned_url(key))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"


def test_blob_name_with_slashes_and_unicode_round_trips():
    """
    Azure Blob is a flat namespace; slashes and unicode are valid characters
    in a blob name. Verify that the same string round-trips through upload,
    SAS sign, and download.
    """
    key = f"products/42/u-{uuid.uuid4().hex}/café.png"
    payload = b"unicode-and-slashes"

    storage.upload_file(key, payload, content_type="application/octet-stream")
    resp = httpx.get(storage.generate_presigned_url(key))

    assert resp.status_code == 200
    assert resp.content == payload


def test_sas_url_for_missing_blob_returns_404_on_download():
    """
    Azure does not check blob existence when generating a SAS — the URL is
    issued unconditionally. The consumer learns the blob is missing when
    they try to download (HTTP 404). This mirrors S3 pre-signed URL behavior.
    """
    key = _unique_key("never-uploaded")
    url = storage.generate_presigned_url(key)
    assert "sig=" in url, "SAS URL should be issued even for missing blobs"

    resp = httpx.get(url)
    assert resp.status_code == 404


def test_sas_url_expiry_reflects_requested_window():
    """
    The 'se' (signed expiry) timestamp on the SAS URL must encode roughly
    the requested expires_in window. We allow a wide tolerance because
    Azurite normalizes timestamps to the second.
    """
    key = _unique_key()
    storage.upload_file(key, b"x", content_type="text/plain")

    issued_at = time.time()
    url = storage.generate_presigned_url(key, expires_in=120)

    se = parse_qs(urlparse(url).query)["se"][0]
    # Azure uses ISO 8601 with a trailing Z; turn it into a timestamp.
    from datetime import datetime
    expiry_ts = datetime.strptime(se, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=__import__("datetime").timezone.utc
    ).timestamp()

    delta = expiry_ts - issued_at
    assert 60 <= delta <= 180, (
        f"SAS expiry should be ~120s in the future; got delta={delta:.1f}s"
    )


def test_get_blob_service_returns_singleton():
    """
    get_blob_service() caches the BlobServiceClient. Multiple callers
    must receive the *same* instance (singleton pattern — same as the
    Redis and Elasticsearch clients).
    """
    a = storage.get_blob_service()
    b = storage.get_blob_service()
    assert a is b


def test_account_key_extraction_from_connection_string():
    """
    storage.generate_presigned_url depends on extracting the AccountKey
    from the connection string via the SDK's parse_connection_str helper
    (a private import). This test pins down that contract — if the SDK
    moves or removes that symbol on upgrade, this test fails loudly
    instead of failing the whole storage layer at runtime.
    """
    from azure.storage.blob._shared.base_client import parse_connection_str

    _primary, _secondary, parsed = parse_connection_str(
        settings.azure_storage_connection_string,
        credential=None,
        service="blob",
    )
    assert "account_key" in parsed
    assert parsed["account_key"], "AccountKey should be non-empty for Azurite dev string"


def test_concurrent_uploads_to_distinct_keys_do_not_clobber():
    """
    Five parallel uploads to *different* keys must produce five readable
    blobs with their respective contents. Catches accidental shared mutable
    state in the BlobServiceClient or upload helper. Uses a thread pool
    (not asyncio) deliberately, to avoid disturbing pytest-asyncio's
    session event loop.
    """
    from concurrent.futures import ThreadPoolExecutor

    keys = [_unique_key(f"concurrent-{i}") for i in range(5)]
    payloads = [f"payload-{i}".encode() for i in range(5)]

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(
            lambda kp: storage.upload_file(kp[0], kp[1], "text/plain"),
            zip(keys, payloads),
        ))

    for key, payload in zip(keys, payloads):
        resp = httpx.get(storage.generate_presigned_url(key))
        assert resp.status_code == 200
        assert resp.content == payload
