"""
routers/orders.py — Checkout and order management endpoints

Routes defined here:
  POST /orders/checkout   — complete a purchase from the active cart
  GET  /orders/{id}       — fetch an existing order by ID

The checkout endpoint is the most critical piece of this application.
It must handle two hard problems simultaneously:

1. Atomicity — all-or-nothing updates
   If we decrement stock for product A and then the server crashes before
   decrementing product B, the database is left in an inconsistent state.
   A PostgreSQL transaction ensures that either ALL changes commit together,
   or NONE of them do.

2. Oversell prevention — concurrent safety
   Two users trying to buy the last item at the same millisecond would both
   read stock=1, both pass the stock check, and both create an order —
   selling the same item twice. SELECT FOR UPDATE prevents this by locking
   each product row so only one transaction can modify it at a time.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.queue import ORDERS_QUEUE, publish
from app.schemas.order import CheckoutRequest, OrderResponse

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/checkout", response_model=OrderResponse, status_code=201)
async def checkout(
    data: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Complete a purchase: validate stock, create the order, decrement inventory.

    Step-by-step flow:
      1. Read the cart from Redis
      2. Open a PostgreSQL transaction
      3. For each product in the cart, lock the row with SELECT FOR UPDATE
      4. Verify stock is sufficient — raise 409 if not
      5. Decrement stock and build the order
      6. Commit the transaction (all changes land in the database at once)
      7. Delete the cart from Redis
      8. Publish an "order.created" event to RabbitMQ for async processing

    Why publish to the queue AFTER the commit?
      If we published before committing and the transaction then rolled back
      (due to a stock conflict or crash), the worker would process an order
      that never actually exists in the database. Always commit first, then
      tell the rest of the world about it.
    """
    redis = await get_redis()

    # Fetch the cart — it is a dict like {"1": "2", "7": "1"}
    cart_key = f"cart:{data.session_id}"
    raw_cart = await redis.hgetall(cart_key)

    if not raw_cart:
        raise HTTPException(status_code=400, detail="Cart is empty or has expired")

    running_total = 0.0

    # We will fill this list inside the transaction so we can create
    # OrderItem rows after we have the order's ID
    order_items_to_create: List[tuple] = []

    # --- Begin the database transaction ---
    # "async with db.begin()" opens a transaction. All database operations
    # inside this block are part of the same transaction. If an exception
    # is raised at any point, the entire transaction rolls back automatically.
    # When the block exits normally, the transaction commits.
    async with db.begin():

        for product_id_str, quantity_str in raw_cart.items():
            product_id = int(product_id_str)
            quantity   = int(quantity_str)

            # SELECT FOR UPDATE locks this product row until the transaction
            # commits. If another transaction has already locked this row,
            # this line will wait until that lock is released.
            #
            # This prevents the oversell race condition:
            #   Transaction A locks the row, checks stock=1, decrements to 0, commits.
            #   Transaction B then gets the lock, checks stock=0 → raises 409.
            lock_query = (
                select(Product)
                .where(Product.id == product_id)
                .with_for_update()
            )
            result = await db.execute(lock_query)

            # scalar_one_or_none() returns the single Product row, or None
            # if no product with that ID exists
            product = result.scalar_one_or_none()

            if product is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Product {product_id} not found",
                )

            if product.stock < quantity:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Insufficient stock for '{product.name}': "
                        f"{product.stock} available, {quantity} requested"
                    ),
                )

            # Decrement stock — this change is part of the transaction
            # and will roll back if anything fails later in this block
            product.stock -= quantity
            running_total += float(product.price) * quantity

            # Save a snapshot of this line item for later
            order_items_to_create.append({
                "product_id":   product.id,
                "product_name": product.name,   # copy the name at time of purchase
                "quantity":     quantity,
                "unit_price":   float(product.price),
            })

        # Create the Order row
        order = Order(
            user_id=data.user_id,
            total=round(running_total, 2),
        )
        db.add(order)

        # flush() sends the INSERT to the database (within the transaction)
        # so PostgreSQL assigns order.id — but the transaction has not committed
        # yet. We need order.id now to create the OrderItem rows that reference it.
        await db.flush()

        # Create one OrderItem row per product in the cart
        for item_data in order_items_to_create:
            order_item = OrderItem(
                order_id=order.id,
                **item_data,
            )
            db.add(order_item)

    # ---- Transaction committed ---
    # All stock decrements and the new order rows are now in PostgreSQL.

    # Remove the cart from Redis — it has been fulfilled
    await redis.delete(cart_key)

    # Invalidate the product cache for every item we just decremented.
    # Without this, a customer browsing a recently-purchased product would
    # see the stock count from BEFORE the purchase (stale by up to the cache
    # TTL — currently 60 seconds). Same cache-invalidation pattern used by
    # `PUT /products/{id}` after a price/stock edit.
    for item_data in order_items_to_create:
        await redis.delete(f"product:{item_data['product_id']}")

    # Publish a message to RabbitMQ. The order_worker.py process will pick
    # this up and send a confirmation email + notify the warehouse.
    await publish(ORDERS_QUEUE, {
        "event":    "order.created",
        "order_id": order.id,
        "user_id":  data.user_id,
        "total":    round(running_total, 2),
    })

    # Reload the order with its items so we can return them in the response.
    # After the transaction ends, the session may not have the items loaded yet.
    order_query = select(Order).where(Order.id == order.id)
    result = await db.execute(order_query)
    order = result.scalar_one()
    await db.refresh(order, ["items"])  # explicitly load the items relationship

    return order


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Fetch an existing order by ID, including all its line items."""
    query = select(Order).where(Order.id == order_id)
    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    # Load the related OrderItem rows before returning
    await db.refresh(order, ["items"])

    return order
