"""
routers/products.py — Product catalog endpoints

Routes defined here:
  POST /products                        — create a product
  GET  /products/search                 — full-text search with filters
  GET  /products/search/autocomplete    — real-time name suggestions
  GET  /products/{id}                   — fetch one product (cached)
  PUT  /products/{id}                   — update a product
  POST /products/{id}/image             — upload a product image
  GET  /products/{id}/image-url         — get a download link for the image

Key patterns demonstrated:
  - Cache-aside: check Redis before querying PostgreSQL
  - Cache invalidation: delete the cache entry when data changes
  - Elasticsearch: full-text search, filters, and autocomplete
  - Object storage: upload files to MinIO/S3, serve via pre-signed URLs
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.database import get_db
from app.models.product import Product
from app.schemas.product import (
    ProductCreate,
    ProductResponse,
    ProductSearchResult,
    ProductUpdate,
)
from app.search import PRODUCTS_INDEX, get_es
from app.storage import generate_presigned_url, upload_file

router = APIRouter(prefix="/products", tags=["products"])

# How long a product stays in the Redis cache before it expires.
# After 60 seconds of no requests, the next fetch goes to PostgreSQL.
CACHE_TTL_SECONDS = 60


def _build_cache_key(product_id: int) -> str:
    """Build the Redis key for a cached product, e.g. "product:42"."""
    return f"product:{product_id}"


async def _index_product_in_elasticsearch(product: Product) -> None:
    """
    Write (or overwrite) a product document in the Elasticsearch index.

    This is called after every create or update so that search results
    always reflect the current state of the product.

    Using str(product.id) as the document ID means re-indexing the same
    product replaces the existing document rather than creating a duplicate.
    """
    es = await get_es()

    await es.index(
        index=PRODUCTS_INDEX,
        id=str(product.id),  # document ID = product ID as a string
        document={
            "id":          product.id,
            "name":        product.name,
            "description": product.description or "",
            "category":    product.category or "",
            "price":       float(product.price),
            "stock":       product.stock,
        },
    )


@router.post("", response_model=ProductResponse, status_code=201)
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new product.

    Saves to PostgreSQL as the source of truth, then indexes in
    Elasticsearch so the product is immediately searchable.
    """
    # data.model_dump() converts the Pydantic model to a plain dictionary.
    # **dict unpacks it so each key becomes a keyword argument to Product().
    product = Product(**data.model_dump())

    db.add(product)
    await db.commit()
    await db.refresh(product)  # populate product.id and product.created_at

    # Index in Elasticsearch so it appears in search results right away
    await _index_product_in_elasticsearch(product)

    return product


@router.get("/search", response_model=List[ProductSearchResult])
async def search_products(
    q: str = "",
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
):
    """
    Search products using Elasticsearch full-text + filters.

    Why Elasticsearch instead of a PostgreSQL LIKE query?
      A PostgreSQL query like WHERE name LIKE '%boots%' scans every row
      in the table. As the catalog grows this becomes slow. Elasticsearch
      uses an inverted index — a map from each word to the documents
      containing it — so lookups are fast regardless of catalog size.
      Elasticsearch also ranks results by relevance (how well they match
      the query), whereas SQL returns all matches with equal weight.

    Query parameters:
      q          — search text, e.g. "hiking boots"
      category   — exact category match, e.g. "footwear"
      min_price  — minimum price in dollars
      max_price  — maximum price in dollars
    """
    es = await get_es()

    # Build the "must" clause — what the document must match.
    # multi_match searches across multiple fields at once.
    # "name^2" means name matches count double (more important than description).
    if q:
        must_clause = [
            {
                "multi_match": {
                    "query":  q,
                    "fields": ["name^2", "description", "category"],
                }
            }
        ]
    else:
        # No search text — return all products (sorted by relevance score later)
        must_clause = [{"match_all": {}}]

    # Build the "filter" clauses — hard constraints that results must satisfy.
    # Filters do not affect the relevance score; they just include/exclude docs.
    filter_clauses = []

    if category:
        # Exact keyword match on the category field
        filter_clauses.append({"term": {"category": category}})

    if min_price is not None or max_price is not None:
        # Build a price range filter with whichever bounds were provided
        price_range = {}

        if min_price is not None:
            price_range["gte"] = min_price  # gte = greater than or equal

        if max_price is not None:
            price_range["lte"] = max_price  # lte = less than or equal

        filter_clauses.append({"range": {"price": price_range}})

    # Combine must (relevance) and filter (hard constraints)
    query = {
        "bool": {
            "must":   must_clause,
            "filter": filter_clauses,
        }
    }

    response = await es.search(index=PRODUCTS_INDEX, query=query, size=20)

    # Build the result list from the Elasticsearch hits.
    # Each hit contains "_source" (the indexed document) and "_score"
    # (the relevance score, 0.0–∞ where higher is better).
    results = []
    for hit in response["hits"]["hits"]:
        results.append(
            ProductSearchResult(
                id=hit["_source"]["id"],
                name=hit["_source"]["name"],
                category=hit["_source"].get("category"),
                price=hit["_source"]["price"],
                score=hit["_score"] or 0.0,
            )
        )

    return results


@router.get("/search/autocomplete")
async def autocomplete(q: str):
    """
    Return product name suggestions as the user types.

    Uses Elasticsearch's "completion" suggester, which is optimized for
    real-time prefix matching. As the user types "hik", it returns
    suggestions like "Hiking Boots", "Hiking Poles", etc.
    """
    es = await get_es()

    response = await es.search(
        index=PRODUCTS_INDEX,
        suggest={
            "name_suggest": {
                "prefix":     q,
                "completion": {"field": "name.suggest"},
            }
        },
    )

    # Navigate the nested response structure to extract suggestion text values.
    # The structure is: suggest → name_suggest → [0] → options → [{text: ...}]
    suggest_results = response.get("suggest", {})
    name_suggest = suggest_results.get("name_suggest", [{}])
    options = name_suggest[0].get("options", [])

    return [option["text"] for option in options]


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch a single product by ID, using the cache-aside pattern.

    Cache-aside (also called "lazy loading"):
      1. Check Redis for the cached product
      2. If found (cache HIT): return immediately — no database query
      3. If not found (cache MISS): query PostgreSQL, store result in
         Redis for next time, then return

    This means the first request for a product hits PostgreSQL, but all
    subsequent requests within the next 60 seconds hit Redis (much faster).
    """
    redis = await get_redis()
    cache_key = _build_cache_key(product_id)

    # Step 1: check the cache
    cached_json = await redis.get(cache_key)

    if cached_json is not None:
        # Cache HIT — deserialize the JSON string back to a ProductResponse object
        return ProductResponse.model_validate_json(cached_json)

    # Step 2: cache MISS — query PostgreSQL
    product = await db.get(Product, product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    # Step 3: store in Redis so the next request is served from cache.
    # model_validate converts the SQLAlchemy object → ProductResponse.
    # model_dump_json() serializes it to a JSON string for storage.
    # setex(key, ttl, value) stores the value and sets it to expire after ttl seconds.
    response = ProductResponse.model_validate(product)
    await redis.setex(cache_key, CACHE_TTL_SECONDS, response.model_dump_json())

    return response


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update product fields. Only the fields included in the request are changed.

    After updating, the Redis cache entry is deleted so the next fetch
    re-reads fresh data from PostgreSQL (cache invalidation). The product
    is also re-indexed in Elasticsearch to keep search results current.
    """
    product = await db.get(Product, product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    # model_dump(exclude_none=True) returns only the fields that were
    # actually provided in the request (skips fields left as None).
    # setattr(obj, field_name, value) sets an attribute by name dynamically.
    fields_to_update = data.model_dump(exclude_none=True)
    for field_name, new_value in fields_to_update.items():
        setattr(product, field_name, new_value)

    await db.commit()
    await db.refresh(product)

    # Delete the stale cache entry — the next GET will repopulate it
    redis = await get_redis()
    await redis.delete(_build_cache_key(product_id))

    # Update Elasticsearch so search results reflect the new price/name/etc.
    await _index_product_in_elasticsearch(product)

    return product


@router.post("/{product_id}/image")
async def upload_product_image(
    product_id: int,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a product image to object storage (MinIO locally, S3 in production).

    Why not store the image in PostgreSQL?
      Binary files in the database bloat backups, slow down queries, and
      consume database connections for file serving. Object storage is
      purpose-built for storing and serving large files cheaply.

    What is stored in PostgreSQL?
      Only the storage key (a short path string like "products/7/photo.jpg").
      The actual bytes live in MinIO/S3. The key is later used to generate
      a pre-signed download URL.
    """
    product = await db.get(Product, product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    # Read the uploaded file bytes
    file_bytes = await file.read()

    # Build a storage path: products/{id}/{filename}
    storage_key = f"products/{product_id}/{file.filename}"

    # Upload to MinIO/S3
    upload_file(storage_key, file_bytes, file.content_type or "application/octet-stream")

    # Save the storage key to PostgreSQL so we can retrieve the image later
    product.image_url = storage_key
    await db.commit()

    return {"key": storage_key, "message": "Image uploaded successfully"}


@router.get("/{product_id}/image-url")
async def get_image_url(
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a temporary, pre-signed download URL for the product image.

    A pre-signed URL is a time-limited link that grants read access to a
    specific file without exposing storage credentials. The client uses
    this URL to download the image directly from MinIO/S3 — the API
    server is not involved in the file transfer.

    The URL expires after 1 hour. Requesting a fresh URL is cheap.
    """
    product = await db.get(Product, product_id)

    if product is None or product.image_url is None:
        raise HTTPException(status_code=404, detail="No image found for this product")

    download_url = generate_presigned_url(product.image_url)

    return {"url": download_url, "expires_in_seconds": 3600}
