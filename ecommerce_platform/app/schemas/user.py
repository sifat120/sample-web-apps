"""
schemas/user.py — Pydantic models for user API requests and responses
"""

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """Request body for creating a new user (POST /users)."""

    # Basic email format validation via min_length.
    # In production you would add email=True or use pydantic's EmailStr.
    email: str = Field(..., min_length=3)

    name: str = Field(..., min_length=1, max_length=255)


class UserResponse(BaseModel):
    """User data returned to the client — does NOT include passwords or secrets."""

    id: int
    email: str
    name: str

    # Allows building this response from a SQLAlchemy User object
    model_config = {"from_attributes": True}
