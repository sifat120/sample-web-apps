"""
search.py — Elasticsearch client and index setup

Elasticsearch is used for product search. Unlike PostgreSQL, which is
optimized for exact lookups (find user with id=5), Elasticsearch is
optimized for relevance-ranked text queries (find products matching
"waterproof hiking boots under $100").

Key concept — the index:
  An Elasticsearch "index" is roughly equivalent to a table in SQL.
  The "mapping" defines the data types for each field, similar to a
  table schema. We define it explicitly so Elasticsearch knows how to
  index each field correctly (text vs. keyword vs. number, etc.).
"""

from elasticsearch import AsyncElasticsearch

from app.config import settings


# Singleton connection — same pattern as cache.py
_es: AsyncElasticsearch | None = None

# The name of the Elasticsearch index that holds all products
PRODUCTS_INDEX = "products"


def _build_es_client_kwargs() -> dict:
    """
    Translate auth settings into the kwargs expected by AsyncElasticsearch.

    Precedence (highest first):
      1. es_api_key            — Elastic Cloud "API keys" UI / data API keys
      2. es_username + es_password — basic auth (Elastic Cloud, Bonsai, self-hosted)
      3. no auth               — local Docker

    Plain URL + basic auth (or API key) covers Elastic Cloud on Azure,
    Bonsai, and any self-hosted Elasticsearch / OpenSearch deployment that
    uses the basic-auth fine-grained access control option.
    """
    kwargs: dict = {}

    if settings.es_api_key:
        kwargs["api_key"] = settings.es_api_key
    elif settings.es_username and settings.es_password:
        kwargs["basic_auth"] = (settings.es_username, settings.es_password)

    return kwargs


async def get_es() -> AsyncElasticsearch:
    """Return the shared Elasticsearch connection, creating it if needed."""
    global _es

    if _es is None:
        _es = AsyncElasticsearch(settings.elasticsearch_url, **_build_es_client_kwargs())

    return _es


async def close_es() -> None:
    """Close the Elasticsearch connection on application shutdown."""
    global _es

    if _es is not None:
        await _es.close()
        _es = None


async def ensure_products_index() -> None:
    """
    Create the products index in Elasticsearch if it does not already exist.

    This runs once at startup. If the index exists, this does nothing.

    Field type explanation:
      "text"     — full-text searchable. Elasticsearch splits the value into
                   individual words and indexes each one, enabling queries like
                   "hiking boots" to match "waterproof hiking boots".

      "keyword"  — exact-match only. Used for filtering (category = "footwear"),
                   not for free-text search.

      "float"    — numeric, used for range filtering (price >= 50).

      "completion" — a special type for autocomplete. Elasticsearch stores
                     prefix data so it can instantly suggest completions as
                     the user types each character.

    The "name" field has three sub-fields:
      name          — main text field for full-text search
      name.suggest  — completion sub-field for autocomplete
      name.keyword  — keyword sub-field for exact matching and sorting
    """
    es = await get_es()

    # Check if the index exists before trying to create it
    index_exists = await es.indices.exists(index=PRODUCTS_INDEX)

    if not index_exists:
        await es.indices.create(
            index=PRODUCTS_INDEX,
            body={
                "mappings": {
                    "properties": {
                        "id":          {"type": "integer"},
                        "name": {
                            "type": "text",
                            "fields": {
                                # Sub-field for autocomplete suggestions
                                "suggest": {"type": "completion"},
                                # Sub-field for exact matching / sorting
                                "keyword": {"type": "keyword"},
                            },
                        },
                        "description": {"type": "text"},
                        # keyword = exact match for category filtering
                        "category":    {"type": "keyword"},
                        "price":       {"type": "float"},
                        "stock":       {"type": "integer"},
                    }
                }
            },
        )
