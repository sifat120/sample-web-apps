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

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_autocomplete_returns_matching_prefix(client: AsyncClient):
    # Use a clearly-distinctive made-up word that no other test can collide with
    unique_token = f"zorblax{uuid.uuid4().hex[:6]}"
    product_name = f"{unique_token} Mountain Boots"

    create = await client.post("/products", json={
        "name": product_name,
        "category": "footwear",
        "price": 99.99,
        "stock": 5,
    })
    assert create.status_code == 201

    # Elasticsearch indexing is asynchronous — wait briefly for the document
    # to become searchable. Poll a few times rather than one fixed sleep so
    # the test stays fast on a warm cluster but tolerant of cold starts.
    suggestions: list[str] = []
    for _ in range(20):
        resp = await client.get(
            f"/products/search/autocomplete?q={unique_token[:5]}"
        )
        assert resp.status_code == 200
        suggestions = resp.json()
        if any(unique_token in s for s in suggestions):
            break
        await asyncio.sleep(0.25)

    assert any(unique_token in s for s in suggestions), (
        f"Expected autocomplete to surface {product_name!r}; got {suggestions!r}"
    )


@pytest.mark.asyncio
async def test_autocomplete_empty_query_returns_list(client: AsyncClient):
    # An empty / unmatchable prefix should still yield a well-formed list (possibly empty).
    resp = await client.get("/products/search/autocomplete?q=zzzzzzzzzzzz_no_match")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
