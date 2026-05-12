"""
Configuration settings for the e-commerce platform.
Uses pydantic-settings to load environment variables from .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn, field_validator
from typing import Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "E-Commerce Platform"
    DEBUG: bool = Field(default=False, alias="DEBUG")
    SECRET_KEY: str = Field(..., alias="SECRET_KEY", description="JWT signing key")
    ALGORITHM: str = Field(default="HS256", alias="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # Database
    DATABASE_URL: str = Field(..., alias="DATABASE_URL", description="Async database URL (e.g., postgresql+asyncpg://... or sqlite+aiosqlite:///...)")
    # Optional fallback for synchronous operations (e.g., Alembic migrations)
    SYNC_DATABASE_URL: Optional[str] = Field(default=None, alias="SYNC_DATABASE_URL")
    # Test database (optional)
    TEST_DATABASE_URL: Optional[str] = Field(default=None, alias="TEST_DATABASE_URL")

    # Redis (optional, for caching/sessions)
    REDIS_URL: Optional[str] = Field(default=None, alias="REDIS_URL")

    # Email (for password reset etc.)
    MAIL_USERNAME: Optional[str] = Field(default=None, alias="MAIL_USERNAME")
    MAIL_PASSWORD: Optional[str] = Field(default=None, alias="MAIL_PASSWORD")
    MAIL_FROM: Optional[str] = Field(default=None, alias="MAIL_FROM")
    MAIL_PORT: int = Field(default=587, alias="MAIL_PORT")
    MAIL_SERVER: Optional[str] = Field(default=None, alias="MAIL_SERVER")
    MAIL_TLS: bool = Field(default=True, alias="MAIL_TLS")
    MAIL_SSL: bool = Field(default=False, alias="MAIL_SSL")

    # CORS
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:8000"], alias="CORS_ORIGINS")

    # Admin credentials for first setup (optional)
    ADMIN_EMAIL: Optional[str] = Field(default=None, alias="ADMIN_EMAIL")
    ADMIN_PASSWORD: Optional[str] = Field(default=None, alias="ADMIN_PASSWORD")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def ensure_async_scheme(cls, v: str) -> str:
        """
        Convert common database URLs to async-compatible ones if needed.
        This handles SQLite and PostgreSQL.
        """
        if v.startswith("sqlite://"):
            # Ensure it uses aiosqlite
            if not v.startswith("sqlite+aiosqlite://"):
                v = v.replace("sqlite://", "sqlite+aiosqlite://", 1)
        elif v.startswith("postgresql://") or v.startswith("postgres://"):
            if "asyncpg" not in v:
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
                v = v.replace("postgres://", "postgres+asyncpg://", 1)
        return v

    @field_validator("SYNC_DATABASE_URL", mode="before")
    @classmethod
    def default_sync_url(cls, v: Optional[str], info) -> Optional[str]:
        """
        If SYNC_DATABASE_URL is not set, derive it from DATABASE_URL by removing async driver.
        """
        if v is not None:
            return v
        db_url = info.data.get("DATABASE_URL")
        if db_url is None:
            return None
        # Replace async schemes with sync ones
        replacements = {
            "sqlite+aiosqlite://": "sqlite://",
            "postgresql+asyncpg://": "postgresql://",
            "postgres+asyncpg://": "postgres://",
        }
        for async_scheme, sync_scheme in replacements.items():
            if db_url.startswith(async_scheme):
                return db_url.replace(async_scheme, sync_scheme, 1)
        return db_url


settings = Settings()