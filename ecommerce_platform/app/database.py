"""
database.py — PostgreSQL connection and session management

This module sets up:
  1. An async SQLAlchemy engine — the low-level connection to PostgreSQL
  2. A session factory — used to create individual database sessions
  3. A base class — all ORM models inherit from this
  4. A dependency function — FastAPI routes call this to get a session

Why async?
  FastAPI is an async web framework. Using async database access means
  the server can handle other requests while waiting for PostgreSQL to
  respond, instead of blocking a thread.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


# The engine manages the connection pool to PostgreSQL.
# echo=False means SQL queries are NOT printed to the console.
# Set echo=True temporarily when debugging to see exact SQL being run.
engine = create_async_engine(settings.postgres_url, echo=False)


# The session factory creates individual database sessions on demand.
# expire_on_commit=False means SQLAlchemy objects remain usable after
# a commit, which is important in async code where lazy loading does
# not work (we need the data to already be loaded).
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.

    Every model (User, Product, Order, etc.) inherits from this class.
    SQLAlchemy uses it to discover all tables and their relationships.
    """
    pass


async def get_db() -> AsyncSession:
    """
    FastAPI dependency that provides a database session to route handlers.

    Usage in a route:
        async def my_route(db: AsyncSession = Depends(get_db)):
            result = await db.execute(...)

    This is a Python "generator" — the `yield` keyword pauses the function
    and gives the session to the route handler. After the route finishes,
    execution resumes here and the session is closed automatically by the
    `async with` block, even if an exception occurred.
    """
    async with AsyncSessionLocal() as session:
        yield session
