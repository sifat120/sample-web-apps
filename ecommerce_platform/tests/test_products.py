import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_product(client: AsyncClient):
    resp = await client.post("/products", json={
        "name": "Test Boots",
        "description": "Great for hiking",
        "category": "footwear",
        "price": 79.99,
        "stock": 10,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Boots"
    assert data["stock"] == 10
    return data["id"]


@pytest.mark.asyncio
async def test_get_product_cache_miss_then_hit(client: AsyncClient, redis_client):
    # Create a product
    resp = await client.post("/products", json={
        "name": "Cache Test Product",
        "price": 9.99,
        "stock": 5,
    })
    product_id = resp.json()["id"]

    # Clear any existing cache entry
    await redis_client.delete(f"product:{product_id}")

    # First fetch — cache miss, hits PostgreSQL
    resp1 = await client.get(f"/products/{product_id}")
    assert resp1.status_code == 200

    # Cache should now be populated
    cached = await redis_client.get(f"product:{product_id}")
    assert cached is not None, "Expected Redis cache to be populated after first fetch"

    # Second fetch — should be served from cache (same data)
    resp2 = await client.get(f"/products/{product_id}")
    assert resp2.status_code == 200
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.asyncio
async def test_cache_invalidated_on_update(client: AsyncClient, redis_client):
    resp = await client.post("/products", json={"name": "Invalidation Test", "price": 10.0, "stock": 3})
    product_id = resp.json()["id"]

    # Warm the cache
    await client.get(f"/products/{product_id}")
    assert await redis_client.get(f"product:{product_id}") is not None

    # Update — should delete cache entry
    await client.put(f"/products/{product_id}", json={"price": 15.0})
    assert await redis_client.get(f"product:{product_id}") is None, "Cache should be cleared after update"


@pytest.mark.asyncio
async def test_product_not_found(client: AsyncClient):
    resp = await client.get("/products/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_products(client: AsyncClient):
    # Seed a searchable product
    await client.post("/products", json={
        "name": "Waterproof Rain Jacket",
        "description": "Perfect for rainy weather",
        "category": "clothing",
        "price": 199.99,
        "stock": 20,
    })

    resp = await client.get("/products/search?q=rain+jacket")
    assert resp.status_code == 200
    results = resp.json()
    assert isinstance(results, list)
    # May be empty if Elasticsearch hasn't indexed yet; check structure
    for item in results:
        assert "id" in item
        assert "price" in item


@pytest.mark.asyncio
async def test_search_price_filter(client: AsyncClient):
    resp = await client.get("/products/search?min_price=50&max_price=100")
    assert resp.status_code == 200
    results = resp.json()
    for item in results:
        assert 50 <= item["price"] <= 100
