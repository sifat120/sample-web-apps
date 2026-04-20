"""
routers/users.py — User management endpoints

Routes defined here:
  POST /users          — register a new user
  GET  /users/{id}     — fetch a user by ID

In a production app, this file would also contain login, password
hashing, JWT token issuance, and profile update endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse

# APIRouter groups related endpoints together.
# prefix="/users" means every route in this file starts with /users.
# tags=["users"] groups these endpoints together in the /docs UI.
router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user account.

    Returns HTTP 409 if the email is already taken.
    Returns HTTP 201 with the new user on success.
    """
    # Check whether a user with this email already exists
    query = select(User).where(User.email == data.email)
    result = await db.execute(query)
    existing_user = result.scalar_one_or_none()  # returns the User or None

    if existing_user is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create the new user object and add it to the session
    new_user = User(email=data.email, name=data.name)
    db.add(new_user)

    # commit() writes the new row to PostgreSQL
    await db.commit()

    # refresh() re-reads the row from the database so new_user.id and
    # new_user.created_at are populated (the DB fills these in on INSERT)
    await db.refresh(new_user)

    return new_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch a user by their ID.

    Returns HTTP 404 if no user with that ID exists.
    """
    user = await db.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return user
