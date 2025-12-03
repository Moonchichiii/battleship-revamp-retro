"""Pytest DB bootstrap: real DB, isolated schema; strictly localhost for testing."""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Generator
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, text

ROOT = Path(__file__).resolve().parents[1]

os.environ.update({
    "TESTING": "true",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "postgres",
    "POSTGRES_DB": "battleship_revamp_test",
})

os.environ.pop("DATABASE_URL", None)

TEST_SCHEMA = f"test_{secrets.token_hex(6)}"


@pytest.fixture(scope="session", autouse=True)
def _db_bootstrap() -> Generator[None, None, None]:
    """Connect, create schema, and create tables inside an isolated test schema."""
    from src.battleship.core.database import Base, engine

    import_module("src.battleship.users.models")

    deadline = time.time() + 10
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                break
        except Exception as e:
            if time.time() > deadline:
                print(f"Could not connect to Test DB: {e}")
                raise
            time.sleep(0.5)

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
