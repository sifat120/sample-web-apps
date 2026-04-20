import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_add_and_get_cart(client: AsyncClient):
    # Use a product we know exists from seed data (id=1, Hiking Boots, stock=50)
    session_id = "test-session-cart-1"

    resp = await client.post(f"/cart/{session_id}/items", json={"product_id": 1, "quantity": 2})
    assert resp.status_code == 200
    assert resp.json()["quantity"] == 2

    cart = await client.get(f"/cart/{session_id}")
    assert cart.status_code == 200
    data = cart.json()
    assert len(data["items"]) >= 1
    assert data["total"] > 0

    # Cleanup
    await client.delete(f"/cart/{session_id}")


@pytest.mark.asyncio
async def test_remove_item_from_cart(client: AsyncClient):
    session_id = "test-session-cart-2"

    await client.post(f"/cart/{session_id}/items", json={"product_id": 1, "quantity": 1})
    await client.post(f"/cart/{session_id}/items", json={"product_id": 2, "quantity": 1})

    resp = await client.delete(f"/cart/{session_id}/items/1")
    assert resp.status_code == 200

    cart = await client.get(f"/cart/{session_id}")
    item_ids = [i["product_id"] for i in cart.json()["items"]]
    assert 1 not in item_ids

    await client.delete(f"/cart/{session_id}")


@pytest.mark.asyncio
async def test_empty_cart(client: AsyncClient):
    resp = await client.get("/cart/nonexistent-session-xyz")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["total"] == 0.0


@pytest.mark.asyncio
async def test_add_invalid_product(client: AsyncClient):
    resp = await client.post("/cart/test-session-bad/items", json={"product_id": 999999, "quantity": 1})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cart_ttl_set(client: AsyncClient, redis_client):
    """Verify that the cart key has a TTL after adding an item."""
    session_id = "test-session-ttl"
    await client.post(f"/cart/{session_id}/items", json={"product_id": 1, "quantity": 1})

    ttl = await redis_client.ttl(f"cart:{session_id}")
    assert ttl > 0, "Cart key should have a TTL set (auto-expiry)"

    await client.delete(f"/cart/{session_id}")
