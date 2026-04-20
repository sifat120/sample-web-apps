"""
tests/conftest.py — Shared pytest fixtures

pytest automatically loads this file before running any tests. The
"fixtures" defined here are reusable pieces of test infrastructure —
things like a connected HTTP client or a Redis connection — that
individual test functions can request by name.

How fixtures work:
  A test function declares a fixture as a parameter:

    async def test_create_product(client: AsyncClient):
        ...

  pytest sees the "client" parameter, finds the fixture with that name
  in conftest.py, runs it, and passes the result to the test function.

  Fixtures with "yield" are generators: code before yield runs at the
  start (setup), code after yield runs at the end (teardown).

Scope:
  scope="session" means the fixture is created once for the entire test
  run and shared across all tests. This avoids reconnecting to services
  on every single test, which would be slow.

  The default scope (no argument) means the fixture is created fresh
  for each individual test function.

Test isolation:
  These tests run against the real local Docker services — the same
  PostgreSQL, Redis, and Elasticsearch that the app uses. Tests that
  create data should use unique IDs or names to avoid interfering with
  each other. Tests that write data to Redis should clean up afterward.
"""

import asyncio
import os

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient

# Set environment variables BEFORE importing the app, so the app's
# config module reads these values instead of whatever is in .env.
# os.environ.setdefault only sets the variable if it is not already set.
os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://postgres:secret@localhost:5432/ecommerce")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ELASTICSEARCH_URL", "http://localhost:9200")
os.environ.setdefault("STORAGE_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("STORAGE_ACCESS_KEY", "minioadmin")
os.environ.setdefault("STORAGE_SECRET_KEY", "minioadmin")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

# Import the FastAPI app AFTER setting environment variables
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """
    Provide a single asyncio event loop for the entire test session.

    By default, pytest-asyncio creates a new event loop per test, which
    would tear down and recreate our session-scoped fixtures on every test.
    This fixture reuses one loop for the whole session to match the
    scope="session" on the client fixture below.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def client():
    """
    An HTTP client connected to the FastAPI app for use in tests.

    ASGITransport routes requests directly to the FastAPI app in-process,
    without opening a real network socket. This makes tests faster and
    more reliable than starting the server as a subprocess.

    Usage in a test:
        async def test_something(client: AsyncClient):
            response = await client.get("/health")
            assert response.status_code == 200
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client


@pytest_asyncio.fixture
async def redis_client():
    """
    A direct Redis connection for tests that need to inspect Redis state.

    Used to verify cache behavior:
      - Does the cache key exist after a GET?
      - Is the key gone after an update (cache invalidation)?
      - Does the cart key have a TTL set?

    This fixture is function-scoped (no scope= argument), so it creates
    a fresh connection for each test and closes it when the test finishes.
    """
    redis = aioredis.from_url("redis://localhost:6379", decode_responses=True)
    yield redis
    await redis.aclose()
