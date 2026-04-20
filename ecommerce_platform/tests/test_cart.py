import uuid

import pytest
from httpx import AsyncClient


def _sid(prefix: str) -> str:
    """Generate a unique cart session id; safe under pytest-xdist parallelism."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_add_and_get_cart(client: AsyncClient):
    # Use a product we know exists from seed data (id=1, Hiking Boots, stock=50)
    session_id = _sid("test-cart-add")

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
    session_id = _sid("test-cart-remove")

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
    resp = await client.get(f"/cart/{_sid('nonexistent')}")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["total"] == 0.0


@pytest.mark.asyncio
async def test_add_invalid_product(client: AsyncClient):
    resp = await client.post(f"/cart/{_sid('test-bad')}/items", json={"product_id": 999999, "quantity": 1})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_to_cart_accumulates_quantity(client: AsyncClient):
    """Adding the same product twice should sum the quantities, not overwrite."""
    session_id = _sid("test-cart-accumulate")

    first = await client.post(f"/cart/{session_id}/items", json={"product_id": 1, "quantity": 2})
    assert first.status_code == 200
    assert first.json()["quantity"] == 2

    second = await client.post(f"/cart/{session_id}/items", json={"product_id": 1, "quantity": 3})
    assert second.status_code == 200
    assert second.json()["quantity"] == 5, "Repeated adds should accumulate (2 + 3 = 5)"

    cart = await client.get(f"/cart/{session_id}")
    line = next(i for i in cart.json()["items"] if i["product_id"] == 1)
    assert line["quantity"] == 5

    await client.delete(f"/cart/{session_id}")


@pytest.mark.asyncio
async def test_add_to_cart_exceeding_stock_returns_400(client: AsyncClient):
    """Adding more units than the product has in stock should return HTTP 400."""
    create = await client.post("/products", json={
        "name": "Tiny Stock Item",
        "price": 1.0,
        "stock": 2,
    })
    product_id = create.json()["id"]
    session_id = f"oversell-add-{product_id}"

    resp = await client.post(
        f"/cart/{session_id}/items",
        json={"product_id": product_id, "quantity": 99},
    )
    assert resp.status_code == 400
    assert "available" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_remove_nonexistent_cart_item_returns_404(client: AsyncClient):
    """Deleting a product that's not in the cart should return 404."""
    resp = await client.delete(f"/cart/{_sid('empty-remove')}/items/1")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cart_quantity_must_be_positive(client: AsyncClient):
    """Pydantic validation should reject quantity 0 / negative with 422."""
    zero = await client.post(f"/cart/{_sid('validate')}/items", json={"product_id": 1, "quantity": 0})
    assert zero.status_code == 422

    negative = await client.post(f"/cart/{_sid('validate')}/items", json={"product_id": 1, "quantity": -1})
    assert negative.status_code == 422


@pytest.mark.asyncio
async def test_cart_ttl_set(client: AsyncClient, redis_client):
    """Verify that the cart key has a TTL after adding an item."""
    session_id = _sid("test-cart-ttl")
    await client.post(f"/cart/{session_id}/items", json={"product_id": 1, "quantity": 1})

    ttl = await redis_client.ttl(f"cart:{session_id}")
    assert ttl > 0, "Cart key should have a TTL set (auto-expiry)"

    await client.delete(f"/cart/{session_id}")
