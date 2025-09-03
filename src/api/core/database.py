"""
Database configuration and utilities for the Battleship Revamp API.

This module sets up the database connection using SQLAlchemy, including
engine creation, session management, and a generator function for database
sessions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from decouple import config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from collections.abc import Generator

raw_url = config(
    "DATABASE_URL",
    default="postgresql://postgres@db:5432/battleship_revamp",
)

# Normalize to psycopg v3 driver
if raw_url.startswith(("postgresql://", "postgres://")):
    raw_url = raw_url.replace("postgres://", "postgresql://", 1)
    raw_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
elif raw_url.startswith("postgresql+psycopg2://"):
    raw_url = raw_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)

DATABASE_URL = raw_url

engine = create_engine(
    DATABASE_URL,
    pool_size=config("DATABASE_POOL_SIZE", cast=int, default=20),
    max_overflow=config("DATABASE_MAX_OVERFLOW", cast=int, default=0),
    pool_timeout=config("DATABASE_POOL_TIMEOUT", cast=int, default=30),
    pool_recycle=config("DATABASE_POOL_RECYCLE", cast=int, default=1800),
    echo=config("SQLALCHEMY_ECHO", cast=bool, default=False),
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
