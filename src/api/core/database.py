"""
Database configuration and utilities for the Battleship Revamp API.

This module sets up the database connection using SQLAlchemy, including
engine creation, session management, and a generator function for database
sessions.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, TypeVar

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

# --- typed env helper ---
T = TypeVar("T")


def _env(key: str, *, default: T, cast: Callable[[str], T] | None = None) -> T:
    val = os.getenv(key)
    if val is None:
        return default
    return cast(val) if cast else val  # type: ignore[return-value]


# --- URL (normalize to psycopg v3) ---
raw_url = _env(
    "DATABASE_URL",
    default="postgresql+psycopg://postgres@db:5432/battleship_revamp",
)

# Accept common variants and coerce to psycopg v3
if raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql://", 1)

if raw_url.startswith("postgresql://"):
    raw_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
elif raw_url.startswith("postgresql+psycopg2://"):
    raw_url = raw_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)

DATABASE_URL = raw_url

# --- Engine options ---
pool_size = _env("DATABASE_POOL_SIZE", default=20, cast=int)
max_overflow = _env("DATABASE_MAX_OVERFLOW", default=0, cast=int)
pool_timeout = _env("DATABASE_POOL_TIMEOUT", default=30, cast=int)
pool_recycle = _env("DATABASE_POOL_RECYCLE", default=1800, cast=int)
echo = _env(
    "SQLALCHEMY_ECHO",
    default=False,
    cast=lambda s: s.strip().lower() in {"1", "true", "yes", "on"},
)

engine = create_engine(
    DATABASE_URL,
    pool_size=pool_size,
    max_overflow=max_overflow,
    pool_timeout=pool_timeout,
    pool_recycle=pool_recycle,
    echo=echo,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """Database session generator."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
