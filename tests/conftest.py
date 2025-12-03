"""Pytest DB bootstrap: real DB, isolated schema; password comes from .env."""

from __future__ import annotations

import os
import secrets
import time
from importlib import import_module
from pathlib import Path
from typing import Any, Generator

import pytest
from decouple import AutoConfig
from sqlalchemy import event, text

# Resolve repo root and load config via python-decouple
ROOT = Path(__file__).resolve().parents[1]
config = AutoConfig(search_path=str(ROOT))

# Tell the app we're in test mode
os.environ["TESTING"] = "true"

# Read connection pieces from .env
host = config("POSTGRES_HOST", default="127.0.0.1")
port = config("POSTGRES_PORT", default="5432")
user = config("POSTGRES_USER", default="postgres")
db = config("POSTGRES_DB", default="battleship_revamp")
password = config("POSTGRES_PASSWORD", default="")

# Force-set env so database.py definitely sees them
os.environ["POSTGRES_HOST"] = host
os.environ["POSTGRES_PORT"] = str(port)
os.environ["POSTGRES_USER"] = user
os.environ["POSTGRES_DB"] = db
if password:
    os.environ["POSTGRES_PASSWORD"] = password
    os.environ["PGPASSWORD"] = password  # libpq fallback

# Avoid any stale URL overriding our settings
os.environ.pop("DATABASE_URL", None)

# Isolated schema per test session
TEST_SCHEMA = f"test_{secrets.token_hex(6)}"


@pytest.fixture(scope="session", autouse=True)
def _db_bootstrap() -> Generator[None, None, None]:
    """Connect, create schema, and create tables inside an isolated test schema."""
    # Import AFTER env is set so engine picks everything up
    from src.battleship.core.database import Base, engine

    # Ensure models are registered
    import_module("src.battleship.users.models")

    # Brief wait for Postgres to be reachable
    deadline = time.time() + 10
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                break
        except Exception:
            if time.time() > deadline:
                raise
            time.sleep(0.5)

    # Create and use isolated schema
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{TEST_SCHEMA}"'))

    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_conn: Any, _: Any) -> None:
        with dbapi_conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{TEST_SCHEMA}", public')

    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{TEST_SCHEMA}" CASCADE'))


@pytest.fixture(autouse=True)
def _db_clean_between_tests() -> Generator[None, None, None]:
    """Truncate tables between tests inside the isolated schema."""
    from src.battleship.core.database import Base, engine

    yield
    tables = ",".join(t.name for t in Base.metadata.sorted_tables)
    if tables:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE;"))