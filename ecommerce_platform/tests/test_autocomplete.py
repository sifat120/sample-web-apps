"""
tests/test_autocomplete.py — Elasticsearch completion suggester test.

The Navbar's search field hits `GET /products/search/autocomplete?q=…`
on every keystroke (debounced) to show name suggestions. That endpoint
relies on the `name.suggest` completion field defined in the products
index mapping.

This test creates a uniquely-named product, gives Elasticsearch a moment
to index it, then verifies the autocomplete suggester returns it for a
prefix of the name.
"""

import asyncio
import uuid

import httpx
import pytest
from httpx import AsyncClient

from app.config import settings
from app.search import PRODUCTS_INDEX


async def _refresh_products_index() -> None:
    """Force a synchronous Elasticsearch refresh so just-indexed documents
    are immediately searchable. Without this the completion suggester
    can lag behind under heavy parallel test load."""
    async with httpx.AsyncClient(timeout=10.0) as http:
        await http.post(f"{settings.elasticsearch_url}/{PRODUCTS_INDEX}/_refresh")


@pytest.mark.asyncio
async def test_autocomplete_returns_matching_prefix(client: AsyncClient):
    # Use a fully-unique prefix so this query can NEVER match a product from
    # a prior test run. We query with the FULL unique_token (12 chars) — the
    # completion suggester returns at most 5 results, so a shorter prefix
    # could be crowded out by accumulated products from previous runs.
    unique_id = uuid.uuid4().hex[:10]
    unique_token = f"zq{unique_id}"
    product_name = f"{unique_token} Mountain Boots"

    create = await client.post("/products", json={
        "name": product_name,
        "category": "footwear",
        "price": 99.99,
        "stock": 5,
    })
    assert create.status_code == 201

    # Force ES to make the new document visible immediately, then poll with
    # a generous deadline (parallel test load can slow ES merges).
    await _refresh_products_index()

    suggestions: list[str] = []
    for _ in range(40):
        resp = await client.get(
            f"/products/search/autocomplete?q={unique_token}"
        )
        assert resp.status_code == 200
        suggestions = resp.json()
        if any(unique_token in s for s in suggestions):
            break
        await asyncio.sleep(0.25)
        await _refresh_products_index()

    assert any(unique_token in s for s in suggestions), (
        f"Expected autocomplete to surface {product_name!r}; got {suggestions!r}"
    )


@pytest.mark.asyncio
async def test_autocomplete_empty_query_returns_list(client: AsyncClient):
    # An empty / unmatchable prefix should still yield a well-formed list (possibly empty).
    resp = await client.get("/products/search/autocomplete?q=zzzzzzzzzzzz_no_match")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
