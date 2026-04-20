"""
queue.py — RabbitMQ connection and message publishing

RabbitMQ is a message queue: a buffer between the web server and
background workers. After a customer checks out, the server publishes
a message ("order #42 was placed") and immediately responds to the
customer. A separate worker process picks up the message and handles
slow tasks like sending emails and notifying the warehouse.

Why use a queue instead of calling those services directly?
  - The customer does not wait for email delivery (slow, external call)
  - If the email service is temporarily down, the message stays in the
    queue and will be retried — no orders are silently dropped
  - Workers can be scaled independently of the web server

Local:      RabbitMQ running in Docker
Production: Replace RABBITMQ_URL with a managed service (e.g. CloudAMQP)
"""

import json
from typing import Optional

import aio_pika

from app.config import settings


# Singleton connection and channel — created once and reused.
# aio_pika types are used for the annotations; the actual objects are
# created in get_channel() below.
_connection: Optional[aio_pika.abc.AbstractConnection] = None
_channel: Optional[aio_pika.abc.AbstractChannel] = None

# The name of the queue that carries post-order messages
ORDERS_QUEUE = "orders"


async def get_channel() -> aio_pika.abc.AbstractChannel:
    """
    Return a connected RabbitMQ channel, reconnecting if necessary.

    Terminology:
      Connection — the TCP connection to the RabbitMQ server
      Channel    — a lightweight virtual connection inside one TCP
                   connection. Most operations (publish, consume) use a
                   channel rather than the connection directly.

    connect_robust() automatically reconnects if the connection drops,
    which can happen when RabbitMQ restarts or the network is unstable.

    durable=True on the queue means the queue survives a RabbitMQ
    restart. Without this, all unprocessed messages would be lost if
    RabbitMQ rebooted.
    """
    global _connection, _channel

    # Reconnect if we have no connection or it has been closed
    if _connection is None or _connection.is_closed:
        _connection = await aio_pika.connect_robust(settings.rabbitmq_url)

    # Re-create the channel if it has been closed
    if _channel is None or _channel.is_closed:
        _channel = await _connection.channel()
        # Declare the queue — safe to call even if it already exists
        await _channel.declare_queue(ORDERS_QUEUE, durable=True)

    return _channel


async def publish(queue_name: str, payload: dict) -> None:
    """
    Publish a JSON message to a RabbitMQ queue.

    Args:
        queue_name: The name of the queue to send to (e.g. "orders")
        payload:    A Python dictionary — will be serialized to JSON

    DeliveryMode.PERSISTENT tells RabbitMQ to write the message to disk
    before acknowledging it. If RabbitMQ crashes before the worker
    processes the message, the message survives and will be delivered
    after restart.
    """
    channel = await get_channel()

    # Serialize the payload dict to JSON bytes for transmission
    message_body = json.dumps(payload).encode()

    message = aio_pika.Message(
        body=message_body,
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,  # survive RabbitMQ restarts
    )

    # The default exchange routes by queue name (routing_key = queue name)
    await channel.default_exchange.publish(message, routing_key=queue_name)


async def close_queue() -> None:
    """Close the RabbitMQ connection on application shutdown."""
    global _connection, _channel

    if _connection is not None and not _connection.is_closed:
        await _connection.close()

    _connection = None
    _channel = None
