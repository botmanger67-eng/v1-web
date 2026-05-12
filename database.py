import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

# Database URL from environment variable, default to SQLite
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./ecommerce.db",
)

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=True, future=True)

# Session factory for async sessions
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Declarative base for models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that returns an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Create all database tables on startup.

    Imports models here to avoid circular imports with the models module.
    """
    # Import all models so they are registered on Base.metadata
    # pylint: disable=unused-import,import-outside-toplevel
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        # Create tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    """Drop all tables (for testing/development only)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)