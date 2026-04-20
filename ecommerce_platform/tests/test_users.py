"""
tests/test_users.py — Granular tests for the /users endpoints.

These tests don't go through the full purchase flow — they exercise the
user CRUD endpoints in isolation:
  - POST /users         creates a user (201)
  - POST /users (dup)   returns 409 when the email is already registered
  - GET  /users/{id}    returns the user
  - GET  /users/9999    returns 404 when the id does not exist

Each test uses a unique email derived from `uuid` so the test suite is
re-runnable without resetting the database between runs.
"""

import uuid

import pytest
from httpx import AsyncClient


def _unique_email(prefix: str) -> str:
    """Generate an email guaranteed not to clash with prior test runs."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}@test.example"


@pytest.mark.asyncio
async def test_create_user_returns_201(client: AsyncClient):
    email = _unique_email("create")
    resp = await client.post("/users", json={"email": email, "name": "Alice"})

    assert resp.status_code == 201
    body = resp.json()
    # The backend assigns the id and returns the full user record
    assert body["id"] > 0
    assert body["email"] == email
    assert body["name"] == "Alice"


@pytest.mark.asyncio
async def test_create_duplicate_email_returns_409(client: AsyncClient):
    email = _unique_email("dup")
    first = await client.post("/users", json={"email": email, "name": "First"})
    assert first.status_code == 201

    # Second create with the SAME email must be rejected
    second = await client.post("/users", json={"email": email, "name": "Second"})
    assert second.status_code == 409
    # The frontend's CheckoutPage relies on this exact detail string to
    # switch to the "enter your user id" fallback flow — keep them in sync.
    assert second.json()["detail"] == "Email already registered"


@pytest.mark.asyncio
async def test_get_user_by_id(client: AsyncClient):
    email = _unique_email("getme")
    created = await client.post("/users", json={"email": email, "name": "Bob"})
    user_id = created.json()["id"]

    resp = await client.get(f"/users/{user_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == user_id
    assert body["email"] == email
    assert body["name"] == "Bob"


@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient):
    # Use an id far above anything any other test would create
    resp = await client.get("/users/999999999")
    assert resp.status_code == 404
