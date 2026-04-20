"""
workers/order_worker.py — Background worker for post-order processing

This script runs as a SEPARATE PROCESS from the API server. It continuously
listens to the "orders" RabbitMQ queue and processes messages that the API
publishes after each successful checkout.

Why a separate process?
  After a customer checks out, we need to:
    - Send them a confirmation email
    - Notify the warehouse to fulfill the order
  These tasks are slow (external API calls) and non-critical to the checkout
  itself. Running them synchronously would make the customer wait. Instead,
  the checkout endpoint publishes a message to the queue and immediately
  returns success. This worker picks up the message and handles the slow
  tasks asynchronously.

How to run:
  In a second terminal (with the API already running):
    python -m workers.order_worker

  In production: deploy this as a separate Docker service or Kubernetes pod.

At-least-once delivery guarantee:
  RabbitMQ guarantees a message is delivered at least once. If this worker
  crashes while processing a message, RabbitMQ will re-deliver the message
  after the worker restarts. This means handlers should be "idempotent" —
  processing the same message twice should have the same effect as once.
  In production, you would track processed order IDs in a database to skip
  messages that have already been handled.
"""

import asyncio
import json
import logging
import os

import aio_pika

# Configure logging to show timestamps and a [worker] label
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(message)s",
)
log = logging.getLogger(__name__)

# Read connection URL from environment, falling back to local Docker default
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
ORDERS_QUEUE = "orders"


async def handle_order_created(payload: dict) -> None:
    """
    Handle a single "order.created" event.

    In a real system, this function would:
      - Call an email service (e.g. SendGrid or Azure Communication Services) to send the receipt
      - Call a warehouse API to trigger fulfillment
      - Update an analytics database with the sale

    For this sample, we log the actions to demonstrate that they are happening
    asynchronously after the checkout response was already returned to the user.
    """
    order_id = payload["order_id"]
    user_id  = payload["user_id"]
    total    = payload["total"]

    # Simulate sending a confirmation email
    log.info(
        f"[EMAIL] Sending order confirmation to user {user_id} "
        f"— order #{order_id}, total ${total:.2f}"
    )

    # Simulate notifying the warehouse
    log.info(f"[WAREHOUSE] Notifying fulfillment team for order #{order_id}")


async def process_message(message: aio_pika.IncomingMessage) -> None:
    """
    Process one message from the queue.

    "async with message.process()" is an aio-pika context manager that:
      - Sends an ACK (acknowledgement) to RabbitMQ when the block exits normally
        — telling RabbitMQ the message was handled and can be removed
      - Sends a NACK (negative acknowledgement) if an exception is raised
        — telling RabbitMQ to re-queue the message for retry

    We re-raise exceptions after logging so the NACK is sent and the
    message goes back into the queue rather than being silently dropped.
    """
    async with message.process():
        try:
            # Decode the JSON bytes back to a Python dictionary
            payload = json.loads(message.body)
            event_type = payload.get("event")

            if event_type == "order.created":
                await handle_order_created(payload)
            else:
                log.warning(f"Received unknown event type: '{event_type}' — skipping")

        except Exception as error:
            log.error(f"Failed to process message: {error}")
            raise  # causes aio-pika to NACK and re-queue the message


async def main() -> None:
    """
    Connect to RabbitMQ and start consuming messages indefinitely.

    prefetch_count=1 means this worker handles one message at a time.
    RabbitMQ will not send the next message until the current one is
    acknowledged. This prevents a single worker from being overwhelmed.
    """
    log.info(f"Connecting to RabbitMQ at {RABBITMQ_URL}")

    # connect_robust() automatically reconnects if the connection drops
    connection = await aio_pika.connect_robust(RABBITMQ_URL)

    async with connection:
        channel = await connection.channel()

        # Only receive one message at a time (fair dispatch)
        await channel.set_qos(prefetch_count=1)

        # Declare the queue — safe to call even if it already exists.
        # durable=True means the queue survives a RabbitMQ restart.
        queue = await channel.declare_queue(ORDERS_QUEUE, durable=True)

        log.info(f"Ready. Waiting for messages on '{ORDERS_QUEUE}'. Press Ctrl+C to stop.")

        # Register our handler function — it will be called for each message
        await queue.consume(process_message)

        # Keep the process running forever until Ctrl+C
        # asyncio.Future() that never resolves acts as an infinite wait
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Worker stopped by user.")
