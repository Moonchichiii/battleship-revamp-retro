"""Database engine/session bootstrap for Battleship (Postgres-only)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

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
        """Initialize the error indicating a missing Postgres password and explain remediation."""
        super().__init__(
            "POSTGRES_PASSWORD missing. Set POSTGRES_PASSWORD, "
            "POSTGRES_PASSWORD_FILE, or provide a Docker secret.",
        )


# ---- Base ------------------------------------------------------------------


class Base(DeclarativeBase):
    """Exported declarative base for ORM models."""


# ---- Helpers ----------------------------------------------------------------


def _read_secret_file(p: str) -> str | None:
    try:
        return Path(p).read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeDecodeError):
        return None


def _get_secret_env(name: str) -> str | None:
    v = os.getenv(name)
    if v:
        return v.strip()

    fp = os.getenv(f"{name}_FILE")
    if fp and Path(fp).exists():
        v = _read_secret_file(fp)
        if v:
            return v

    guess = Path(f"/run/secrets/{name.lower()}")
    if guess.exists():
        v = _read_secret_file(str(guess))
        if v:
            return v
    return None


def _env_bool(key: str, *, default: bool = False) -> bool:
    raw = os.getenv(key)
    return default if raw is None else raw.lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


# ---- Mode flags -------------------------------------------------------------
# True when running under pytest or explicitly set via env.
TESTING: Final[bool] = os.getenv("PYTEST_CURRENT_TEST") is not None or _env_bool(
    "TESTING",
    default=False,
)


# ---- DATABASE_URL resolution (Postgres only) --------------------------------

_database_url = (os.getenv("DATABASE_URL") or "").strip()
_test_database_url = (os.getenv("TEST_DATABASE_URL") or "").strip()
if _database_url:
    norm = _database_url.replace("postgres://", "postgresql://", 1)
    if norm.startswith("postgresql+psycopg2://"):
        norm = norm.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    elif norm.startswith("postgresql://"):
        norm = norm.replace("postgresql://", "postgresql+psycopg://", 1)
    try:
        DATABASE_URL = str(make_url(norm))
    except ArgumentError as e:
        details = str(e)
        raise InvalidDatabaseURLError(details) from e
elif TESTING and _test_database_url:
    # Prefer a dedicated test URL when testing
    try:
        DATABASE_URL = str(
            make_url(
                _test_database_url.replace("postgres://", "postgresql://", 1).replace(
                    "postgresql+psycopg2://",
                    "postgresql+psycopg://",
                    1,
                ),
            ),
        )
    except ArgumentError as e:
        raise InvalidDatabaseURLError(str(e)) from e
else:
    PG_USER = os.getenv("POSTGRES_USER", "postgres")
    PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
    PG_PORT = os.getenv("POSTGRES_PORT", "5432")
    PG_DB = os.getenv("POSTGRES_DB", "battleship_revamp")
    PG_PASSWORD = _get_secret_env("POSTGRES_PASSWORD")

    # In tests, don't fail hard at import-time if the password isn't present.
    if not PG_PASSWORD and not TESTING:
        raise MissingPostgresPasswordError

    auth_part = f":{quote_plus(PG_PASSWORD)}" if PG_PASSWORD else ""
    DATABASE_URL = (
        f"postgresql+psycopg://{quote_plus(PG_USER)}{auth_part}"
        f"@{PG_HOST}:{PG_PORT}/{PG_DB}"
    )

engine = create_engine(
    DATABASE_URL,
    pool_size=_env_int("DATABASE_POOL_SIZE", 20),
    max_overflow=_env_int("DATABASE_MAX_OVERFLOW", 0),
    pool_timeout=_env_int("DATABASE_POOL_TIMEOUT", 30),
    pool_recycle=_env_int("DATABASE_POOL_RECYCLE", 1800),
    pool_pre_ping=True,
    echo=_env_bool("SQLALCHEMY_ECHO", default=False),
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


__all__ = ["TESTING", "Base", "SessionLocal", "engine", "get_db"]
