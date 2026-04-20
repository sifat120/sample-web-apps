"""Checkout tests — covering the ACID transaction and oversell prevention."""
import asyncio
import uuid

import pytest
from httpx import AsyncClient


async def _seed_product(client: AsyncClient, stock: int) -> int:
    resp = await client.post("/products", json={
        "name": f"Limited Item (stock={stock})",
        "price": 49.99,
        "stock": stock,
    })
    assert resp.status_code == 201
    return resp.json()["id"]


async def _seed_user(client: AsyncClient, prefix: str) -> int:
    """Create a user with a guaranteed-unique email so re-runs never collide."""
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@test.example"
    resp = await client.post("/users", json={"email": email, "name": "Test User"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_checkout_happy_path(client: AsyncClient):
    user_id = await _seed_user(client, "buyer1")
    product_id = await _seed_product(client, stock=10)
    session_id = f"checkout-session-{product_id}"

    await client.post(f"/cart/{session_id}/items", json={"product_id": product_id, "quantity": 2})

    resp = await client.post("/orders/checkout", json={"session_id": session_id, "user_id": user_id})
    assert resp.status_code == 201
    order = resp.json()
    assert order["status"] == "confirmed"
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == 2
    assert abs(order["total"] - 99.98) < 0.01

    # Stock should have decremented
    product_resp = await client.get(f"/products/{product_id}")
    assert product_resp.json()["stock"] == 8


@pytest.mark.asyncio
async def test_checkout_insufficient_stock(client: AsyncClient):
    """Attempting to buy more than available stock returns HTTP 409."""
    user_id = await _seed_user(client, "buyer2")
    product_id = await _seed_product(client, stock=1)
    session_id = f"checkout-low-{product_id}"

    # Try to buy 5, but only 1 in stock
    await client.post(f"/cart/{session_id}/items", json={"product_id": product_id, "quantity": 5})

    # Override cart quantity directly — cart validation only checks stock at add time
    import redis.asyncio as aioredis
    r = aioredis.from_url("redis://localhost:6379", decode_responses=True)
    await r.hset(f"cart:{session_id}", str(product_id), "5")
    await r.aclose()

    resp = await client.post("/orders/checkout", json={"session_id": session_id, "user_id": user_id})
    assert resp.status_code == 409
    assert "Insufficient stock" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_checkout_empty_cart(client: AsyncClient):
    user_id = await _seed_user(client, "buyer3")
    resp = await client.post("/orders/checkout", json={"session_id": "empty-session-xyz", "user_id": user_id})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_checkout_clears_cart(client: AsyncClient, redis_client):
    """After a successful checkout, the cart should be deleted from Redis."""
    user_id = await _seed_user(client, "buyer4")
    product_id = await _seed_product(client, stock=5)
    session_id = f"checkout-clear-{product_id}"

    await client.post(f"/cart/{session_id}/items", json={"product_id": product_id, "quantity": 1})
    await client.post("/orders/checkout", json={"session_id": session_id, "user_id": user_id})

    cart_exists = await redis_client.exists(f"cart:{session_id}")
    assert cart_exists == 0, "Cart should be deleted from Redis after checkout"


@pytest.mark.asyncio
async def test_oversell_prevention_concurrent(client: AsyncClient):
    """Two concurrent checkout attempts for the last unit — exactly one should succeed.

    This test simulates the classic oversell race condition. With SELECT FOR UPDATE,
    the database serializes the two transactions and the second one sees stock=0.
    """
    user_id = await _seed_user(client, "buyer5")
    product_id = await _seed_product(client, stock=1)

    session_a = f"concurrent-a-{product_id}"
    session_b = f"concurrent-b-{product_id}"

    import redis.asyncio as aioredis
    r = aioredis.from_url("redis://localhost:6379", decode_responses=True)
    await r.hset(f"cart:{session_a}", str(product_id), "1")
    await r.hset(f"cart:{session_b}", str(product_id), "1")
    await r.aclose()

    results = await asyncio.gather(
        client.post("/orders/checkout", json={"session_id": session_a, "user_id": user_id}),
        client.post("/orders/checkout", json={"session_id": session_b, "user_id": user_id}),
    )

    statuses = [r.status_code for r in results]
    assert 201 in statuses, "At least one checkout should succeed"
    assert 409 in statuses or 400 in statuses, "The other checkout should fail (no stock)"
    assert statuses.count(201) == 1, "Exactly one checkout should succeed — no oversell"


@pytest.mark.asyncio
async def test_get_order_returns_persisted_order(client: AsyncClient):
    """A successful checkout should produce an order retrievable via GET /orders/{id}."""
    user_id = await _seed_user(client, "buyer-get")
    product_id = await _seed_product(client, stock=4)
    session_id = f"order-get-{product_id}"

    await client.post(f"/cart/{session_id}/items", json={"product_id": product_id, "quantity": 2})
    checkout = await client.post(
        "/orders/checkout", json={"session_id": session_id, "user_id": user_id}
    )
    assert checkout.status_code == 201
    order_id = checkout.json()["id"]

    fetched = await client.get(f"/orders/{order_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["id"] == order_id
    assert body["user_id"] == user_id
    assert len(body["items"]) == 1
    assert body["items"][0]["product_id"] == product_id
    assert body["items"][0]["quantity"] == 2


@pytest.mark.asyncio
async def test_get_order_not_found(client: AsyncClient):
    resp = await client.get("/orders/999999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_checkout_invalidates_product_cache(client: AsyncClient, redis_client):
    """After checkout, the product's cache entry must be deleted so the next GET
    reflects the decremented stock instead of returning a stale cached value."""
    user_id = await _seed_user(client, "buyer-cache")
    product_id = await _seed_product(client, stock=5)
    session_id = f"checkout-cache-{product_id}"

    # Warm the cache so we can prove it gets invalidated
    await client.get(f"/products/{product_id}")
    assert await redis_client.get(f"product:{product_id}") is not None

    await client.post(f"/cart/{session_id}/items", json={"product_id": product_id, "quantity": 2})
    checkout = await client.post(
        "/orders/checkout", json={"session_id": session_id, "user_id": user_id}
    )
    assert checkout.status_code == 201

    cached = await redis_client.get(f"product:{product_id}")
    assert cached is None, "Product cache must be invalidated after checkout"

    # Next read should reflect the new stock (5 - 2 = 3) from PostgreSQL
    refreshed = await client.get(f"/products/{product_id}")
    assert refreshed.json()["stock"] == 3
