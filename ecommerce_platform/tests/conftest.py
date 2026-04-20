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


def pytest_configure(config):
    """
    Register custom pytest markers used by this test suite.

    `cloud` marks tests that require a real Microsoft Azure Storage
    account (not Azurite). They are skipped by default; set the
    AZURE_CLOUD_TESTS=1 environment variable to opt in. See
    tests/test_azure_cloud.py for usage.
    """
    config.addinivalue_line(
        "markers",
        "cloud: tests that hit real Azure cloud services; "
        "skipped unless AZURE_CLOUD_TESTS=1 is set",
    )


def pytest_collection_modifyitems(config, items):
    """
    Auto-skip any test marked @pytest.mark.cloud when AZURE_CLOUD_TESTS
    is not enabled. This keeps `pytest tests/` fast and offline-friendly
    by default while still allowing one-command opt-in for cloud runs.
    """
    if os.environ.get("AZURE_CLOUD_TESTS") == "1":
        return  # opt-in active — let cloud tests run

    skip_cloud = pytest.mark.skip(
        reason="Cloud tests skipped (set AZURE_CLOUD_TESTS=1 to enable)"
    )
    for item in items:
        if "cloud" in item.keywords:
            item.add_marker(skip_cloud)

# Set environment variables BEFORE importing the app, so the app's
# config module reads these values instead of whatever is in .env.
# os.environ.setdefault only sets the variable if it is not already set.
os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://postgres:secret@localhost:5432/ecommerce")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ELASTICSEARCH_URL", "http://localhost:9200")
os.environ.setdefault(
    "AZURE_STORAGE_CONNECTION_STRING",
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://localhost:10000/devstoreaccount1;",
)
os.environ.setdefault("AZURE_STORAGE_CONTAINER", "product-images")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
# Disable the cart router's per-IP rate limit during tests. With pytest-xdist
# every worker hits the loopback IP, so the production default of 100 req/min
# is easy to exhaust in a parallel run and would manifest as spurious 429s.
os.environ.setdefault("CART_RATE_LIMIT_MAX_REQUESTS", "1000000")

# Import the FastAPI app AFTER setting environment variables
from app.config import settings
from app.main import app
from app.search import PRODUCTS_INDEX
from app.storage import ensure_container


def _ensure_products_index_sync() -> None:
    """
    Idempotently create the Elasticsearch products index using a plain
    HTTP request (no async client). The async client created by
    `app.search.ensure_products_index` binds to whichever event loop is
    active at construction time; pytest-asyncio creates a new loop per
    test, so reusing the bootstrap-created client across tests fails
    with "Timeout context manager should be used inside a task".

    Going over raw HTTP here keeps the bootstrap loop-agnostic and
    matches the behavior of the FastAPI lifespan (which runs in the
    server's loop and creates its own client per process).
    """
    import httpx

    base = settings.elasticsearch_url.rstrip("/")
    index_url = f"{base}/{PRODUCTS_INDEX}"
    if httpx.head(index_url).status_code == 200:
        return

    httpx.put(index_url, json={
        "mappings": {
            "properties": {
                "id":          {"type": "integer"},
                "name": {
                    "type": "text",
                    "fields": {
                        "suggest": {"type": "completion"},
                        "keyword": {"type": "keyword"},
                    },
                },
                "description": {"type": "text"},
                "category":    {"type": "keyword"},
                "price":       {"type": "float"},
                "stock":       {"type": "integer"},
            }
        }
    }).raise_for_status()


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_services():
    """
    Recreate the same backing-service preconditions that the FastAPI
    lifespan handler creates on real startup. ASGITransport (used by
    the in-process test client) does not fire lifespan events.

    Also clears any leftover `rate:*` keys in Redis. The cart router
    rate-limits per-IP at 100 req/min; back-to-back parallel test runs
    from the same loopback IP can otherwise inherit a counter from a
    previous run and trigger spurious 429s.
    """
    ensure_container()
    _ensure_products_index_sync()

    # Clear rate-limit keys synchronously via redis-py's sync client.
    try:
        import redis as _sync_redis  # redis-py ships sync + async APIs

        url = settings.redis_url
        r = _sync_redis.from_url(url)
        for key in r.scan_iter(match="rate:*", count=500):
            r.delete(key)
        r.close()
    except Exception:
        # Best-effort cleanup; tests will still surface real failures.
        pass

    yield


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
