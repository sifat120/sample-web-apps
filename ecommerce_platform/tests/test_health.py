"""
tests/test_health.py — /health endpoint smoke tests.

The health endpoint pings all three core backing services and returns a
status string per service. Monitoring tools and load balancers call this
endpoint to decide whether to send traffic to an instance.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_all_services(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200

    body = resp.json()
    # The three services we always check
    assert set(body.keys()) == {"redis", "postgres", "elasticsearch"}


@pytest.mark.asyncio
async def test_health_all_services_ok(client: AsyncClient):
    """When the docker compose stack is healthy, every service should report 'ok'."""
    resp = await client.get("/health")
    body = resp.json()

    for service, status in body.items():
        # If a service is misconfigured we get a string like
        # "error: Connection refused" — assert positively on "ok" so any
        # such failure mode produces a clear test message.
        assert status == "ok", f"{service} reported: {status}"
