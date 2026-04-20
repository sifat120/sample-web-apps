"""
schemas/order.py — Pydantic models for cart and order API requests and responses

The cart and order flows share this file because they are tightly coupled:
the cart schema describes what goes INTO the cart, and the order schemas
describe what comes OUT of a checkout.
"""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class CartItem(BaseModel):
    """Request body for adding an item to the cart (POST /cart/{session_id}/items)."""

    product_id: int

    # ge=1 means quantity must be 1 or more — you can't add 0 items
    quantity: int = Field(..., ge=1)


class CheckoutRequest(BaseModel):
    """Request body for the checkout endpoint (POST /orders/checkout)."""

    # The session ID identifies the cart in Redis, e.g. "user-browser-abc123"
    session_id: str

    # The user who is placing the order — links to the users table
    user_id: int


class OrderItemResponse(BaseModel):
    """One line item within an order response."""

    product_id: int
    product_name: str
    quantity: int
    unit_price: float

    # from_attributes=True allows this model to be built from a SQLAlchemy
    # OrderItem object (not just a plain dictionary)
    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    """Full order details returned after checkout or when fetching an order."""

    id: int
    user_id: int
    status: str
    total: float
    created_at: datetime

    # A list of the individual products within this order
    items: List[OrderItemResponse]

    model_config = {"from_attributes": True}
