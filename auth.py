import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Assuming project structure with core/settings, models/user, db/session
from app.core.config import settings  # provides SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.db.session import get_db
from app.models.user import User
from app.schemas.token import TokenData  # optional, but good practice

# Password hashing context (bcrypt recommended for production)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme: expects token in Authorization header as "Bearer <token>"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")  # adjust endpoint path as needed


# ----------------------------------------------------------------------
# Password utilities
# ----------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


# ----------------------------------------------------------------------
# JWT token utilities
# ----------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token with an expiration time.

    Args:
        data: Dictionary containing claims (must include 'sub' for user identifier).
        expires_delta: Optional custom expiration time. If None, uses default from settings.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT token.

    Args:
        token: Encoded JWT string.

    Returns:
        Decoded payload dictionary.

    Raises:
        JWTError: If token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ----------------------------------------------------------------------
# Dependency to get current authenticated user
# ----------------------------------------------------------------------

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    FastAPI dependency that extracts and validates the JWT token,
    then fetches the corresponding user from the database.

    Args:
        token: Bearer token from request header.
        db: Database session (injected).

    Returns:
        User model instance.

    Raises:
        HTTPException 401 if token invalid or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception

    # Optional: store token data in a Pydantic model for extra validation
    token_data = TokenData(username=username)

    # Fetch user from database (assuming username is unique and stored in username field)
    # Adjust field name if your model uses 'email' instead
    result = await db.execute(select(User).where(User.username == token_data.username))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    # Optional: check if user is active/disabled if applicable
    # if not user.is_active:
    #     raise HTTPException(status_code=400, detail="Inactive user")

    return user


# ----------------------------------------------------------------------
# Optional convenience alias for endpoints that require admin role
# ----------------------------------------------------------------------

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to ensure the current user is active (not disabled).
    Modify according to your user model's activation flag.
    """
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_current_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Dependency to ensure the current user has admin role.
    Modify according to your user model's role field.
    """
    if not current_user.is_admin:  # adjust to match your model (e.g., role == 'admin')
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user