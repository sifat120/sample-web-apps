"""
tests/test_e2e_purchase.py — End-to-end purchase flow.

A single test that walks through the entire customer journey, exercising
every backing service in one shot:

  PostgreSQL   → create user, create product, persist order rows
  Elasticsearch → index product, search & retrieve it
  MinIO/S3     → upload an image, generate a pre-signed download URL
  Valkey       → add to cart (hash + TTL), cache product detail, clear cart
  RabbitMQ     → publish "order.created" message after successful checkout

If this single test passes, every service-to-service hand-off in the
system is wired correctly. If it fails, the failing assertion narrows the
problem down to a specific hand-off (DB, cache, search, storage, queue).
"""

import asyncio
import json
import uuid

import aio_pika
import httpx
import pytest
from httpx import AsyncClient

from app.queue import ORDERS_QUEUE


# Tiny valid PNG so the image-upload step has real bytes to send.
TINY_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452"
    "0000000100000001080600000031c0c2"
    "1100000005494441547801631800001a"
    "00010d0a2db40000000049454e44ae42"
    "6082"
)


@pytest.mark.asyncio
async def test_full_purchase_flow_end_to_end(client: AsyncClient, redis_client):
    # ===============================================================
    # Step 1 — Register a user (PostgreSQL)
    # ===============================================================
    email = f"e2e-{uuid.uuid4().hex[:8]}@test.example"
    user_resp = await client.post(
        "/users",
        json={"email": email, "name": "E2E Buyer"},
    )
    assert user_resp.status_code == 201, "user creation should succeed"
    user_id = user_resp.json()["id"]

    # ===============================================================
    # Step 2 — Create a product (PostgreSQL + Elasticsearch indexing)
    # ===============================================================
    distinctive_token = f"e2eitem{uuid.uuid4().hex[:6]}"
    product_resp = await client.post("/products", json={
        "name": f"{distinctive_token} Premium Backpack",
        "description": "End-to-end test backpack",
        "category": "outdoors",
        "price": 79.99,
        "stock": 3,
    })
    assert product_resp.status_code == 201
    product = product_resp.json()
    product_id = product["id"]
    assert product["stock"] == 3

    # ===============================================================
    # Step 3 — Upload a product image (MinIO/S3) and verify roundtrip
    # ===============================================================
    upload = await client.post(
        f"/products/{product_id}/image",
        files={"file": ("backpack.png", TINY_PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 200

    img_url_resp = await client.get(f"/products/{product_id}/image-url")
    assert img_url_resp.status_code == 200
    presigned_url = img_url_resp.json()["url"]

    async with httpx.AsyncClient(timeout=10.0) as net:
        img_dl = await net.get(presigned_url)
    assert img_dl.status_code == 200
    assert img_dl.content == TINY_PNG_BYTES, "image bytes survived the round-trip"

    # ===============================================================
    # Step 4 — Search finds the new product (Elasticsearch)
    # ===============================================================
    # Indexing is async — poll briefly until the new doc is searchable.
    found = False
    for _ in range(20):
        search = await client.get(
            f"/products/search?q={distinctive_token}"
        )
        assert search.status_code == 200
        if any(hit["id"] == product_id for hit in search.json()):
            found = True
            break
        await asyncio.sleep(0.25)
    assert found, "Newly created product should appear in Elasticsearch search results"

    # ===============================================================
    # Step 5 — Fetch detail twice to exercise the cache-aside path (Valkey)
    # ===============================================================
    cache_key = f"product:{product_id}"
    # Make sure no stale cache entry survives from a prior test run
    await redis_client.delete(cache_key)

    first_detail = await client.get(f"/products/{product_id}")
    assert first_detail.status_code == 200
    assert await redis_client.get(cache_key) is not None, "cache miss should populate Redis"

    second_detail = await client.get(f"/products/{product_id}")
    assert second_detail.status_code == 200
    assert second_detail.json() == first_detail.json(), "cached payload must match the source"

    # ===============================================================
    # Step 6 — Add 2 units to the cart (Valkey hash + TTL)
    # ===============================================================
    session_id = f"e2e-session-{product_id}"
    add_resp = await client.post(
        f"/cart/{session_id}/items",
        json={"product_id": product_id, "quantity": 2},
    )
    assert add_resp.status_code == 200

    cart_resp = await client.get(f"/cart/{session_id}")
    assert cart_resp.status_code == 200
    cart = cart_resp.json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 2
    assert abs(cart["total"] - 159.98) < 0.01

    # The cart hash should have a TTL so it auto-expires on abandonment
    cart_ttl = await redis_client.ttl(f"cart:{session_id}")
    assert cart_ttl > 0

    # ===============================================================
    # Step 7 — Drain the orders queue so we can assert on a fresh message
    # ===============================================================
    drain_conn = await aio_pika.connect_robust("amqp://guest:guest@localhost:5672/")
    try:
        async with drain_conn:
            ch = await drain_conn.channel()
            q = await ch.declare_queue(ORDERS_QUEUE, durable=True)
            while True:
                m = await q.get(no_ack=False, fail=False)
                if m is None:
                    break
                await m.ack()
    finally:
        if not drain_conn.is_closed:
            await drain_conn.close()

    # ===============================================================
    # Step 8 — Checkout (PostgreSQL transaction + Valkey cleanup + RabbitMQ publish)
    # ===============================================================
    checkout = await client.post(
        "/orders/checkout",
        json={"session_id": session_id, "user_id": user_id},
    )
    assert checkout.status_code == 201, checkout.text
    order = checkout.json()
    order_id = order["id"]

    assert order["user_id"] == user_id
    assert order["status"] == "confirmed"
    assert len(order["items"]) == 1
    assert order["items"][0]["product_id"] == product_id
    assert order["items"][0]["quantity"] == 2
    assert abs(order["total"] - 159.98) < 0.01

    # Cart should be gone from Redis after checkout
    assert await redis_client.exists(f"cart:{session_id}") == 0

    # ===============================================================
    # Step 9 — Stock decremented in PostgreSQL (3 - 2 = 1)
    # ===============================================================
    after_resp = await client.get(f"/products/{product_id}")
    assert after_resp.status_code == 200
    assert after_resp.json()["stock"] == 1

    # ===============================================================
    # Step 10 — Order is retrievable + RabbitMQ received the event
    # ===============================================================
    fetched = await client.get(f"/orders/{order_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == order_id

    # Pop the message off the queue and verify its contents
    consume_conn = await aio_pika.connect_robust("amqp://guest:guest@localhost:5672/")
    try:
        ch = await consume_conn.channel()
        q = await ch.declare_queue(ORDERS_QUEUE, durable=True)

        message_body = None
        deadline = asyncio.get_event_loop().time() + 5.0
        while asyncio.get_event_loop().time() < deadline:
            msg = await q.get(no_ack=False, fail=False)
            if msg is not None:
                async with msg.process():
                    message_body = json.loads(msg.body.decode())
                break
            await asyncio.sleep(0.1)
    finally:
        if not consume_conn.is_closed:
            await consume_conn.close()

    assert message_body is not None, "checkout should publish to RabbitMQ"
    assert message_body == {
        "event":    "order.created",
        "order_id": order_id,
        "user_id":  user_id,
        "total":    round(159.98, 2),
    }
