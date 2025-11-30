"""Database engine/session bootstrap for Battleship (Postgres-only)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import quote_plus

from decouple import config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Iterator

# ---- Exceptions -------------------------------------------------------------


class InvalidDatabaseURLError(RuntimeError):
    """Raised when DATABASE_URL cannot be parsed/normalized."""

    def __init__(self, details: str | None = None) -> None:
        """Initialize the InvalidDatabaseURLError with optional details."""
        msg = "Invalid DATABASE_URL"
        if details:
            msg = f"{msg}: {details}"
        super().__init__(msg)


class MissingPostgresPasswordError(RuntimeError):
    """Raised when no Postgres password is provided via env/secret."""

    def __init__(self) -> None:
        """Initialize the error indicating a missing Postgres password."""
        super().__init__(
            "POSTGRES_PASSWORD missing. Set POSTGRES_PASSWORD, "
            "POSTGRES_PASSWORD_FILE, or provide a Docker secret at /run/secrets/postgres_password",
        )


# ---- Base ------------------------------------------------------------------


class Base(DeclarativeBase):
    """Exported declarative base for ORM models."""


# ---- Helpers ----------------------------------------------------------------


def _read_secret_file(p: str) -> str | None:
    """Read secret from file path, return None if not readable."""
    try:
        return Path(p).read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeDecodeError):
        return None


def _get_secret_env(name: str) -> str | None:
    """Get secret from env var, env file, or Docker secret location."""
    # Direct environment variable using decouple (typed)
    value: str | None = config(name, default=None, cast=str)
    if value:
        return value.strip()

    try:
        file_path: str | None = config(f"{name}_FILE", default=None, cast=str)
        if file_path and Path(file_path).exists():
            secret_value = _read_secret_file(file_path)
            if secret_value is not None:
                return secret_value
    except (TypeError, ValueError, OSError):
        logger.exception("Failed to read secret file for %s", name)

    # Docker secrets convention
    docker_secret_path = Path(f"/run/secrets/{name.lower()}")
    if docker_secret_path.exists():
        secret_value = _read_secret_file(str(docker_secret_path))
        if secret_value is not None:
            return secret_value

    return None


def _normalize_postgres_url(url: str) -> str:
    """Normalize postgres:// URLs to postgresql+psycopg:// format."""
    # Handle legacy postgres:// URLs
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Convert to psycopg driver
    if url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    return url


def _build_postgres_url() -> str:
    """Build PostgreSQL URL from component environment variables."""
    pg_user = config("POSTGRES_USER", default="postgres")
    pg_host = config("POSTGRES_HOST", default="localhost")
    pg_port = config("POSTGRES_PORT", default="5432")
    pg_db = config("POSTGRES_DB", default="battleship_revamp")
    pg_password = _get_secret_env("POSTGRES_PASSWORD")

    # In testing mode, use the test database name if not explicitly set
    if TESTING:
        # Use battleship_revamp_test for testing unless overridden
        test_db_name = config("POSTGRES_TEST_DB", default="battleship_revamp_test")
        pg_db = test_db_name

    # Password is required in production, but handle testing scenarios
    if not pg_password:
        # In testing, allow passwordless only if explicitly enabled
        if TESTING and config("ALLOW_PASSWORDLESS_DB", default=False, cast=bool):
            return f"postgresql+psycopg://{quote_plus(pg_user)}@{pg_host}:{pg_port}/{pg_db}"
        # Always require password for non-test environments
        raise MissingPostgresPasswordError

    # Build URL with password (normal case for local dev and production)
    auth_part = f":{quote_plus(pg_password)}"
    return (
        f"postgresql+psycopg://{quote_plus(pg_user)}{auth_part}"
        f"@{pg_host}:{pg_port}/{pg_db}"
    )


def _get_database_url() -> str:
    """Get database URL with proper priority order."""
    # 1. Explicit DATABASE_URL (highest priority)
    database_url = config("DATABASE_URL", default=None)
    if database_url:
        return _normalize_postgres_url(database_url.strip())

    # 2. Test database URL (testing only)
    if TESTING:
        test_url = config("TEST_DATABASE_URL", default=None)
        if test_url:
            return _normalize_postgres_url(test_url.strip())

    # 3. Build from components
    return _build_postgres_url()


# ---- Mode flags -------------------------------------------------------------

TESTING: Final[bool] = config(
    "PYTEST_CURRENT_TEST",
    default=None,
) is not None or config("TESTING", default=False, cast=bool)

# ---- Database URL resolution ------------------------------------------------

try:
    DATABASE_URL = _get_database_url()
    # Validate URL can be parsed
    make_url(DATABASE_URL)
except ArgumentError as e:
    raise InvalidDatabaseURLError(str(e)) from e

# ---- Engine and Session Setup -----------------------------------------------

engine = create_engine(
    DATABASE_URL,
    pool_size=config("DATABASE_POOL_SIZE", default=20, cast=int),
    max_overflow=config("DATABASE_MAX_OVERFLOW", default=0, cast=int),
    pool_timeout=config("DATABASE_POOL_TIMEOUT", default=30, cast=int),
    pool_recycle=config("DATABASE_POOL_RECYCLE", default=1800, cast=int),
    pool_pre_ping=True,
    echo=config("SQLALCHEMY_ECHO", default=False, cast=bool),
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """Yield a SQLAlchemy Session and ensure it is closed."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["DATABASE_URL", "TESTING", "Base", "SessionLocal", "engine", "get_db"]
