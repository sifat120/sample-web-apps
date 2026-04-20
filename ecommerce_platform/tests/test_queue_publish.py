"""
tests/test_queue_publish.py — RabbitMQ integration test for checkout.

When `POST /orders/checkout` succeeds, the API publishes an
`order.created` event to the `orders` queue. A separate worker process
consumes this queue to send confirmation emails and notify the warehouse.

This test verifies the publish side of that contract:
  1. Drain whatever messages are sitting in the queue (so prior test
     runs don't pollute our assertions).
  2. Place a real order via the API.
  3. Pop a single message off the queue and assert it contains the
     expected event name + order id + user id + total.

If this test fails, the worker would never receive new orders in
production — a high-impact bug to catch.
"""

import asyncio
import json

import aio_pika
import pytest
from httpx import AsyncClient

from app.queue import ORDERS_QUEUE


RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"


async def _drain_queue() -> None:
    """Pop and ack every existing message so the queue is empty."""
    conn = await aio_pika.connect_robust(RABBITMQ_URL)
    try:
        async with conn:
            channel = await conn.channel()
            queue = await channel.declare_queue(ORDERS_QUEUE, durable=True)
            while True:
                msg = await queue.get(no_ack=False, fail=False)
                if msg is None:
                    return
                await msg.ack()
    finally:
        if not conn.is_closed:
            await conn.close()


async def _wait_for_order_message(order_id: int, timeout: float = 15.0) -> dict | None:
    """Pop messages until we find one matching `order_id`.

    With pytest-xdist, multiple workers publish to the same `orders` queue.
    A naive "pop the next message" would race — worker A might consume
    worker B's message. Strategy: consume messages without acking; only ack
    the one with our `order_id`. When the channel closes, RabbitMQ
    automatically requeues all unacked messages so other workers can still
    see them.
    """
    conn = await aio_pika.connect_robust(RABBITMQ_URL)
    try:
        # Use a dedicated channel; closing it requeues anything we left unacked.
        channel = await conn.channel()
        # Limit prefetch so a single consumer can't hoard the entire queue.
        await channel.set_qos(prefetch_count=50)
        queue = await channel.declare_queue(ORDERS_QUEUE, durable=True)

        seen_other_tags: list = []
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            msg = await queue.get(no_ack=False, fail=False)
            if msg is None:
                await asyncio.sleep(0.1)
                continue
            try:
                body = json.loads(msg.body.decode())
            except Exception:
                await msg.ack()
                continue
            if body.get("order_id") == order_id:
                await msg.ack()
                # Closing the channel requeues the rest for other workers.
                await channel.close()
                return body
            # Not ours — keep it unacked so it stays "in flight" for now.
            seen_other_tags.append(msg)
            # If we've buffered too many, recycle the channel to release them.
            if len(seen_other_tags) >= 40:
                await channel.close()
                channel = await conn.channel()
                await channel.set_qos(prefetch_count=50)
                queue = await channel.declare_queue(ORDERS_QUEUE, durable=True)
                seen_other_tags.clear()
        # Timeout — close to release everything we held.
        if not channel.is_closed:
            await channel.close()
        return None
    finally:
        if not conn.is_closed:
            await conn.close()


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="rabbitmq")
async def test_checkout_publishes_order_created_event(client: AsyncClient):
    # ---- Arrange ----
    # Create the user + product the test needs
    user_resp = await client.post(
        "/users",
        json={"email": "queue-test@test.example", "name": "Queue Tester"},
    )
    # 409 means a previous test run created this user — re-fetch them.
    if user_resp.status_code == 409:
        # We can't look up by email, so just create a unique one this run.
        import uuid
        user_resp = await client.post(
            "/users",
            json={
                "email": f"queue-test-{uuid.uuid4().hex[:8]}@test.example",
                "name": "Queue Tester",
            },
        )
    user_id = user_resp.json()["id"]

    prod_resp = await client.post("/products", json={
        "name": "Queue Test Widget",
        "price": 12.34,
        "stock": 10,
    })
    product_id = prod_resp.json()["id"]
    session_id = f"queue-test-session-{product_id}"

    # Add 3 units to the cart → expected total = 12.34 * 3 = 37.02
    await client.post(
        f"/cart/{session_id}/items",
        json={"product_id": product_id, "quantity": 3},
    )

    # Drain the queue first; safe under xdist because this test is in the
    # "rabbitmq" xdist_group which serializes RabbitMQ-touching tests.
    await _drain_queue()

    # ---- Act ----
    checkout = await client.post(
        "/orders/checkout",
        json={"session_id": session_id, "user_id": user_id},
    )
    assert checkout.status_code == 201
    order_id = checkout.json()["id"]

    # ---- Assert ----
    message = await _wait_for_order_message(order_id, timeout=10.0)
    assert message is not None, "Expected an order.created message on the queue"

    assert message["event"] == "order.created"
    assert message["order_id"] == order_id
    assert message["user_id"] == user_id
    assert abs(message["total"] - 37.02) < 0.01
