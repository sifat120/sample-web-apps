"""
models/product.py — Product database model

Maps to the "products" table in PostgreSQL.

Key design notes:
  - price uses Numeric(10, 2) — stores exact decimal values, avoiding
    the floating-point rounding errors that come with float columns.
    e.g. $19.99 is stored as exactly 19.99, not 19.990000000000001.

  - stock must be >= 0 (enforced in the SQL schema via CHECK constraint).
    The ORM model does not re-enforce this; the database is the final guard.

  - seller_id is optional (nullable). A product created without a seller
    is still valid — useful for seeded demo data.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Text allows unlimited length — suitable for long product descriptions.
    # Optional[str] means this column can be NULL (no description provided).
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Short category label, e.g. "footwear", "camping". Optional.
    category: Mapped[Optional[str]] = mapped_column(String(100))

    # Numeric(10, 2): up to 10 digits total, 2 after the decimal point.
    # This ensures prices like $9999999.99 are stored exactly.
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Current units available in inventory
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Which seller owns this product. Optional — nullable foreign key.
    seller_id: Mapped[Optional[int]] = mapped_column(Integer)

    # Path to the product image in object storage (MinIO/S3), e.g.:
    # "products/7/photo.jpg". The actual file lives in object storage;
    # this string is used to generate a pre-signed download URL.
    image_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Set automatically by the database when the row is first created
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Updated automatically by the database whenever the row is modified.
    # onupdate=func.now() sets this to the current timestamp on every UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
