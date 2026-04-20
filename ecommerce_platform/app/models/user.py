"""
models/user.py — User database model

This file defines the "users" table using SQLAlchemy's ORM (Object
Relational Mapper). Instead of writing raw SQL to create or query rows,
we work with Python objects (User instances) and SQLAlchemy translates
them to SQL automatically.

How Mapped[] works:
  Mapped[str] means "this column holds a string and is required (NOT NULL)"
  Mapped[str | None] means "this column holds a string OR can be NULL"
  mapped_column(...) provides additional column-level constraints like
  max length, uniqueness, and default values.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    # __tablename__ tells SQLAlchemy which database table this class maps to
    __tablename__ = "users"

    # Primary key — auto-incremented integer, unique per row
    id: Mapped[int] = mapped_column(primary_key=True)

    # String(255) sets a max length of 255 characters.
    # unique=True adds a database-level UNIQUE constraint (no two users
    # can share the same email).
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # server_default=func.now() means the database fills this in automatically
    # when a row is inserted. This is more reliable than setting it in Python
    # because it uses the database server's clock, not the app server's clock.
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
