"""
main.py — FastAPI application entry point

This file does three things:
  1. Defines the application lifespan (startup and shutdown logic)
  2. Registers all route groups (users, products, cart, orders)
  3. Exposes the /health endpoint for monitoring

Starting the app:
  uvicorn app.main:app --reload

  "app.main" = the Python module path (app/main.py)
  "app"      = the variable name of the FastAPI instance in that file
  --reload   = auto-restart when code changes (development only)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.cache import close_redis, get_redis
from app.database import AsyncSessionLocal, engine
from app.queue import close_queue, get_channel
from app.routers import cart, orders, products, users
from app.search import close_es, ensure_products_index, get_es
from app.storage import ensure_container


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown.

    This is a Python "async context manager". The code before `yield`
    runs when the app starts. The code after `yield` runs when the app
    shuts down. FastAPI calls this automatically.

    Why connect here instead of at the top of each module?
      Connecting during startup means the app fails fast if a service
      is unreachable, rather than failing silently on the first request.
    """
    # --- Startup ---
    await get_redis()                # open Redis connection
    await get_es()                   # open Elasticsearch connection
    await ensure_products_index()    # create ES index if it doesn't exist
    ensure_container()               # create the Azure Blob container if it doesn't exist

    # RabbitMQ connection is optional at startup — the worker runs as a
    # separate process and the queue connection will be established on
    # the first checkout. We attempt it here so errors surface early,
    # but we don't crash if RabbitMQ is temporarily unavailable.
    try:
        await get_channel()
    except Exception:
        pass

    yield  # application runs here, handling requests

    # --- Shutdown ---
    await close_redis()
    await close_es()
    await close_queue()
    await engine.dispose()  # close all PostgreSQL connections in the pool


# Create the FastAPI application instance.
# All configuration, middleware, and routes attach to this object.
app = FastAPI(
    title="E-Commerce Platform",
    description="Sample e-commerce API demonstrating PostgreSQL, Redis, Elasticsearch, Azure Blob Storage, and RabbitMQ.",
    version="1.0.0",
    lifespan=lifespan,
)

# Register route groups.
# Each router is defined in its own file under app/routers/.
# include_router attaches all its routes to the main app.
app.include_router(users.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(orders.router)


@app.get("/health", tags=["health"])
async def health():
    """
    Check whether each backing service is reachable.

    Returns a dictionary with "ok" or an error message per service.
    Monitoring tools and load balancers call this endpoint to decide
    whether to send traffic to this instance.

    Example response:
        {"redis": "ok", "postgres": "ok", "elasticsearch": "ok"}
    """
    status = {}

    # Check Redis
    try:
        redis = await get_redis()
        await redis.ping()
        status["redis"] = "ok"
    except Exception as error:
        status["redis"] = f"error: {error}"

    # Check PostgreSQL by running the simplest possible query
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        status["postgres"] = "ok"
    except Exception as error:
        status["postgres"] = f"error: {error}"

    # Check Elasticsearch
    try:
        es = await get_es()
        await es.ping()
        status["elasticsearch"] = "ok"
    except Exception as error:
        status["elasticsearch"] = f"error: {error}"

    return status
