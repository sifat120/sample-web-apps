"""
tests/test_storage_and_images.py — Object storage (Azurite/Azure Blob) roundtrip.

These tests verify the full image lifecycle:
  1. POST /products/{id}/image      → upload bytes to Azurite
  2. GET  /products/{id}/image-url  → returns a SAS download URL
  3. HTTP GET on the SAS URL        → returns the same bytes we uploaded

Plus a 404 case for products that have no image yet.

Why use raw httpx for step 3?
  The SAS URL points at Azurite directly (http://localhost:10000/...),
  not at the FastAPI app. We need a real network client, not the
  in-process ASGI transport, to fetch it.
"""

import httpx
import pytest
from httpx import AsyncClient


# A 1×1 transparent PNG — small enough to embed inline. Azurite doesn't
# care about format; this is just convenient real-looking image bytes.
TINY_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452"
    "0000000100000001080600000031c0c2"
    "1100000005494441547801631800001a"
    "00010d0a2db40000000049454e44ae42"
    "6082"
)


async def _create_product_for_image(client: AsyncClient) -> int:
    """Helper: create a product and return its id."""
    resp = await client.post("/products", json={
        "name": "Image Test Product",
        "price": 19.99,
        "stock": 1,
    })
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_image_upload_and_presigned_download_roundtrip(client: AsyncClient):
    product_id = await _create_product_for_image(client)

    # ---- Step 1: upload the image bytes ----
    upload = await client.post(
        f"/products/{product_id}/image",
        files={"file": ("tiny.png", TINY_PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 200, upload.text
    upload_body = upload.json()
    assert upload_body["key"] == f"products/{product_id}/tiny.png"

    # ---- Step 2: ask the API for a SAS download URL ----
    url_resp = await client.get(f"/products/{product_id}/image-url")
    assert url_resp.status_code == 200
    sas_url = url_resp.json()["url"]

    # The URL targets Azurite (or real Azure Blob in production). Azure
    # SAS query strings include a `sig=` parameter holding the HMAC.
    assert "sig=" in sas_url, f"Expected an Azure SAS signature in the URL, got: {sas_url}"

    # ---- Step 3: fetch the URL with a real HTTP client ----
    # ASGITransport (used for the `client` fixture) only routes to the
    # FastAPI app, so we open a separate httpx.AsyncClient here.
    async with httpx.AsyncClient(timeout=10.0) as net_client:
        download = await net_client.get(sas_url)

    assert download.status_code == 200, download.text
    # Most importantly: the bytes we get back must match what we uploaded.
    # This proves the upload landed in the right blob and wasn't corrupted.
    assert download.content == TINY_PNG_BYTES


@pytest.mark.asyncio
async def test_image_url_404_when_no_image_uploaded(client: AsyncClient):
    """A product with no image should not return a SAS URL."""
    product_id = await _create_product_for_image(client)

    resp = await client.get(f"/products/{product_id}/image-url")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_image_for_missing_product_returns_404(client: AsyncClient):
    resp = await client.post(
        "/products/999999999/image",
        files={"file": ("x.png", TINY_PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 404

