"""
models/order.py — Order and OrderItem database models

An order represents a single completed purchase. It has a one-to-many
relationship with order items: one order can contain many line items
(e.g. 2x Hiking Boots + 1x Backpack).

Database structure:
  orders table      → one row per completed checkout
  order_items table → one row per product within an order

Why store product_name on the order item?
  Product names can change over time. By copying the name at the moment
  of purchase, we ensure that viewing an old order always shows the
  correct name, even if the seller later renamed the product.

SQLAlchemy relationships:
  The relationship() call adds a Python attribute that lets you navigate
  between related objects without writing a JOIN query manually:

    order = await db.get(Order, order_id)
    for item in order.items:   # automatically fetches related OrderItems
        print(item.product_name)
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    # The customer who placed this order
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Current state of the order, e.g. "confirmed", "shipped", "delivered"
    status: Mapped[str] = mapped_column(String(50), default="confirmed")

    # Total price for all items combined, stored as exact decimal
    total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # "items" is a Python-side relationship attribute — not a real database column.
    # SQLAlchemy uses it to automatically load the related OrderItem rows.
    # back_populates="order" creates the reverse link: item.order gives back
    # the parent Order object.
    items: Mapped[List["OrderItem"]] = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign key links this item to its parent order.
    # ON DELETE CASCADE (in the SQL schema) means if the order is deleted,
    # its items are automatically deleted too.
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)

    # Reference to the product — we store the ID and also copy the name
    # (see module docstring for why)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # How many units of this product were purchased
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Price per unit at the time of purchase (copied from the product)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # The reverse relationship — lets you navigate from an item back to its order
    order: Mapped["Order"] = relationship("Order", back_populates="items")
