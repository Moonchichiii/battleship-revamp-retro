"""Test bootstrap for Battleship: spins up schema and isolates test data."""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from collections.abc import Iterator

# --- Environment FIRST (before importing app code) ---
ROOT = Path(__file__).resolve().parents[1]

# Minimal required env for app under test
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(32))
os.environ.setdefault("TESTING", "true")

# Prefer CI-provided DATABASE_URL. If missing, fall back to local secret file.
if "DATABASE_URL" not in os.environ:
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        pw_path = ROOT / "secrets" / "postgres_password.txt"
        if pw_path.exists():
            password = pw_path.read_text(encoding="utf-8-sig").strip()
    if password:
        os.environ.setdefault(
            "DATABASE_URL",
            f"postgresql+psycopg://postgres:{password}@127.0.0.1:6543/battleship_revamp_test",
        )

DB_URL = os.environ.get("DATABASE_URL", "")


def _with_ct(url: str, seconds: int = 3) -> str:
    if not url:
        return url
    s = urlsplit(url)
    q = dict(parse_qsl(s.query))
    q.setdefault("connect_timeout", str(seconds))
    return urlunsplit((s.scheme, s.netloc, s.path, urlencode(q), s.fragment))


if DB_URL:
    DB_URL = _with_ct(DB_URL, 3)
    os.environ["DATABASE_URL"] = DB_URL

# Safety guards: never let tests hit a prod/shared DB by mistake.
_NON_LOCAL_MSG = "Refusing to run tests against a non-local database."
_WRONG_NAME_MSG = "Test DB must be named *_test."
if DB_URL:
    if "127.0.0.1" not in DB_URL and "localhost" not in DB_URL:
        raise RuntimeError(_NON_LOCAL_MSG)
    if "battleship_revamp_test" not in DB_URL:
        raise RuntimeError(_WRONG_NAME_MSG)

# Optional: prefer Alembic migrations if available
try:
    from alembic import command
    from alembic.config import Config

    def _run_migrations() -> None:
        """Apply Alembic migrations up to head for the test DB."""
        cfg = Config(str(ROOT / "alembic.ini"))
        if DB_URL:
            cfg.set_main_option("sqlalchemy.url", DB_URL)
        command.upgrade(cfg, "head")

    USE_MIGRATIONS = True
except ImportError:
    USE_MIGRATIONS = False


@pytest.fixture(scope="session", autouse=True)
def _db_bootstrap() -> Iterator[None]:
    """Wait for DB readiness, then create schema (migrations or metadata)."""
    # Import DB bits only after env is set to avoid E402.
    from src.api.core.database import Base, engine

    # Wait for the DB to be ready
    for _ in range(120):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except SQLAlchemyError:
            time.sleep(0.5)

    if USE_MIGRATIONS:
        _run_migrations()
    else:
        Base.metadata.create_all(bind=engine)

    yield

    # Tear down only when we didn't use migrations
    if not USE_MIGRATIONS:
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _db_clean_between_tests() -> Iterator[None]:
    """Truncate all tables between tests so state never leaks."""
    from src.api.core.database import Base, engine

    yield
    tables = ",".join(t.name for t in Base.metadata.sorted_tables)
    if tables:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE;"))


@pytest.fixture()
def client() -> TestClient:
    """FastAPI test client."""
    # Import app only after env is set to avoid E402 and early side effects.
    from main import app

    return TestClient(app)
