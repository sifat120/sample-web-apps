"""
schemas/product.py — Pydantic models for product API requests and responses

Pydantic models serve two purposes:
  1. Validation: incoming request bodies are automatically validated against
     these models. If a required field is missing or has the wrong type,
     FastAPI returns HTTP 422 with a clear error message before the route
     handler even runs.
  2. Serialization: response objects are converted to JSON using these models,
     ensuring only the intended fields are exposed to the client.

Separate models for Create, Update, and Response:
  We define different models for each use case rather than reusing one model.
  This prevents accidental exposure of internal fields (like seller_id) in
  responses, and ensures update endpoints only accept fields they're allowed
  to change.

Field(...) syntax:
  The "..." (Ellipsis) as the first argument means the field is required —
  there is no default value. Named arguments like min_length, gt, ge add
  validation rules:
    gt=0  means "greater than 0" (price must be positive)
    ge=0  means "greater than or equal to 0" (stock can be zero)
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    """Fields required when creating a new product (POST /products)."""

    # name is required and must be between 1 and 255 characters
    name: str = Field(..., min_length=1, max_length=255)

    description: Optional[str] = None
    category: Optional[str] = None

    # price is required and must be greater than 0
    price: float = Field(..., gt=0)

    # stock is required and must be 0 or more (can't start with negative stock)
    stock: int = Field(..., ge=0)

    # seller_id is optional — can be omitted for demo/seed data
    seller_id: Optional[int] = None


class ProductUpdate(BaseModel):
    """
    Fields that can be updated (PUT /products/{id}).

    Every field is Optional — the client only needs to send the fields
    they want to change. Fields not included in the request are left
    unchanged in the database.
    """
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    stock: Optional[int] = Field(None, ge=0)


class ProductResponse(BaseModel):
    """
    Shape of the product data returned to the client.

    model_config = {"from_attributes": True} tells Pydantic to read
    field values from object attributes (like a SQLAlchemy model instance)
    rather than from a dictionary. Without this, ProductResponse.model_validate(product)
    would fail because SQLAlchemy objects are not plain dicts.
    """
    id: int
    name: str
    description: Optional[str]
    category: Optional[str]
    price: float
    stock: int
    seller_id: Optional[int]
    image_url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductSearchResult(BaseModel):
    """Lightweight response shape for search results — no description or timestamps."""
    id: int
    name: str
    category: Optional[str]
    price: float
    # Relevance score assigned by Elasticsearch (higher = better match)
    score: float
