"""
Shared Dependencies for FastAPI E-Commerce Platform

This module provides the core dependencies used across the application:
- async database session (get_db)
- current authenticated user (get_current_user)
- current admin user (get_current_admin)
"""

from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.config import settings  # expects settings.SECRET_KEY, settings.ALGORITHM
from app.database import async_session_maker  # async session factory
from app.models import User  # SQLAlchemy model for users

# OAuth2 scheme: expects token from login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session.

    Yields:
        AsyncSession: The database session.
    Closes the session after use.
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode JWT token and return the authenticated user.

    Args:
        token: Bearer token from Authorization header.
        db: Database session.

    Returns:
        User: The authenticated user.

    Raises:
        HTTPException 401: If token is invalid or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the current user has admin role.

    Args:
        current_user: Authenticated user from dependency.

    Returns:
        User: The admin user.

    Raises:
        HTTPException 403: If user is not an admin.
    """
    if not current_user.is_admin:  # assuming User model has 'is_admin' boolean
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action",
        )
    return current_user