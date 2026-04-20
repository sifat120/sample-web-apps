"""
routers/cart.py — Shopping cart endpoints

Routes defined here:
  POST   /cart/{session_id}/items          — add a product to the cart
  GET    /cart/{session_id}                — view the cart with product details
  DELETE /cart/{session_id}/items/{id}     — remove one product from the cart
  DELETE /cart/{session_id}               — clear the entire cart

Why Redis instead of PostgreSQL for the cart?
  The cart is temporary — if a user abandons their session, the cart
  should disappear automatically. Redis TTL (time-to-live) handles this
  without any cleanup jobs. Redis is also much faster than PostgreSQL for
  this kind of read-heavy, small-payload data.

Cart data structure in Redis:
  Key:    "cart:{session_id}"   e.g. "cart:abc-browser-xyz"
  Type:   Redis Hash (like a dictionary)
  Fields: product_id → quantity  e.g. {"1": "2", "7": "1"}

  This means product 1 is in the cart with quantity 2, and product 7
  with quantity 1.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.database import get_db
from app.models.product import Product
from app.schemas.order import CartItem

router = APIRouter(prefix="/cart", tags=["cart"])

# Cart auto-expires 24 hours after the last interaction
CART_TTL_SECONDS = 60 * 60 * 24   # 86400 seconds = 24 hours

# Rate limiting constants
RATE_LIMIT_WINDOW_SECONDS = 60    # count requests over a 1-minute sliding window
RATE_LIMIT_MAX_REQUESTS = 100     # max requests per IP per window


def _build_cart_key(session_id: str) -> str:
    """Build the Redis key for a cart, e.g. "cart:abc123"."""
    return f"cart:{session_id}"


async def _enforce_rate_limit(redis, client_ip: str) -> None:
    """
    Prevent a single IP from making too many requests per minute.

    How it works:
      1. Increment a Redis counter keyed by IP address: INCR rate:1.2.3.4
      2. On the first increment (count == 1), set the key to expire after
         60 seconds — this resets the counter automatically each minute.
      3. If the count exceeds the limit, reject the request with HTTP 429.

    Redis's INCR command is atomic — even under concurrent requests from
    the same IP, the counter is always accurate.
    """
    rate_key = f"rate:{client_ip}"

    # Atomically increment the counter and get the new value
    current_count = await redis.incr(rate_key)

    if current_count == 1:
        # First request in this window — set the expiry so the key
        # disappears automatically after RATE_LIMIT_WINDOW_SECONDS
        await redis.expire(rate_key, RATE_LIMIT_WINDOW_SECONDS)

    if current_count > RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please slow down.",
        )


@router.post("/{session_id}/items", status_code=200)
async def add_to_cart(
    session_id: str,
    item: CartItem,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Add a product to the cart (or increase its quantity if already present).

    The session_id comes from the URL path. In a real frontend, this would
    be generated client-side (e.g. a UUID stored in localStorage or a cookie)
    and sent with every cart request.
    """
    redis = await get_redis()

    # Rate limiting — reject abusive callers before doing any DB work
    await _enforce_rate_limit(redis, request.client.host)

    # Validate the product exists in PostgreSQL
    product = await db.get(Product, item.product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.stock < item.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Only {product.stock} units available",
        )

    cart_key = _build_cart_key(session_id)

    # hget reads one field from the Redis hash. If the product is not yet
    # in the cart, it returns None — we default that to 0.
    existing_quantity_str = await redis.hget(cart_key, str(item.product_id))
    existing_quantity = int(existing_quantity_str or 0)

    new_quantity = existing_quantity + item.quantity

    # hset sets one field in the hash: cart_key[product_id] = new_quantity
    await redis.hset(cart_key, str(item.product_id), new_quantity)

    # Reset the TTL so the cart survives for another 24h from this interaction
    await redis.expire(cart_key, CART_TTL_SECONDS)

    return {
        "session_id": session_id,
        "product_id": item.product_id,
        "quantity":   new_quantity,
    }


@router.get("/{session_id}")
async def get_cart(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Return all items in the cart with full product details and a total.

    hgetall returns the entire Redis hash as a dictionary:
      {"1": "2", "7": "1"} → product 1 qty 2, product 7 qty 1

    We then look up each product in PostgreSQL to get the current name
    and price (in case they changed since the item was added).
    """
    redis = await get_redis()
    cart_key = _build_cart_key(session_id)

    # hgetall returns an empty dict {} if the key does not exist
    raw_cart = await redis.hgetall(cart_key)

    if not raw_cart:
        return {"session_id": session_id, "items": [], "total": 0.0}

    items = []
    running_total = 0.0

    for product_id_str, quantity_str in raw_cart.items():
        product_id = int(product_id_str)
        quantity = int(quantity_str)

        product = await db.get(Product, product_id)

        # Skip items whose product was deleted since being added to the cart
        if product is None:
            continue

        item_price = float(product.price)
        subtotal = item_price * quantity
        running_total += subtotal

        items.append({
            "product_id": product.id,
            "name":       product.name,
            "price":      item_price,
            "quantity":   quantity,
            "subtotal":   round(subtotal, 2),
        })

    return {
        "session_id": session_id,
        "items":      items,
        "total":      round(running_total, 2),
    }


@router.delete("/{session_id}/items/{product_id}", status_code=200)
async def remove_from_cart(session_id: str, product_id: int):
    """Remove a single product from the cart."""
    redis = await get_redis()

    # hdel removes one field from the Redis hash and returns the number of
    # fields actually removed (0 if the field didn't exist)
    fields_removed = await redis.hdel(_build_cart_key(session_id), str(product_id))

    if fields_removed == 0:
        raise HTTPException(status_code=404, detail="Item not found in cart")

    return {"removed_product_id": product_id}


@router.delete("/{session_id}", status_code=200)
async def clear_cart(session_id: str):
    """Delete the entire cart from Redis. Called automatically after checkout."""
    redis = await get_redis()
    await redis.delete(_build_cart_key(session_id))
    return {"cleared_session": session_id}
