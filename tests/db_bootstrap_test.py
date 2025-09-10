"""Boot a throwaway Postgres via Testcontainers and prove PG types (INET) work."""

from __future__ import annotations

import contextlib
import os
import socket
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from testcontainers.postgres import PostgresContainer

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import TypeVar

    T = TypeVar("T")


def fixture(*_args: object, **_kwargs: object) -> object:
    """Typing stub for pytest.fixture used by tooling/linters."""
    return pytest.fixture(*_args, **_kwargs)


def fail(msg: str, *_args: object, **_kwargs: object) -> None:
    """Typing stub for pytest.fail used by tooling/linters."""
    pytest.fail(msg, *_args, **_kwargs)


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
        except OSError:
            return False
        else:
            return True


# Environment-driven DB bootstrap (used when DATABASE_URL is provided)
DB_URL = os.getenv("DATABASE_URL")
USE_MIGRATIONS = os.getenv("USE_MIGRATIONS", "").lower() in {"1", "true", "yes"}


def _run_migrations() -> None:
    """Attempt to run alembic migrations (if alembic is available)."""
    try:
        import alembic.command as _cmd
        import alembic.config as _ac
    except Exception as exc:  # pragma: no cover - best-effort
        msg = "Alembic not available to run migrations"
        raise RuntimeError(msg) from exc

    alembic_ini = os.getenv("ALEMBIC_INI", "alembic.ini")
    cfg = _ac.Config(alembic_ini)
    _cmd.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _db_bootstrap() -> Iterator[None]:
    """Wait briefly for DB, then create schema (migrations or metadata)."""
    # Import lazily so tests that don't need DB won't import DB machinery prematurely.
    from src.api.core.database import Base, engine

    url = make_url(DB_URL) if DB_URL else None
    host = (url.host or "127.0.0.1") if url else "127.0.0.1"
    port = (url.port or 5432) if url else 5432

    # Fail fast if the port never opens
    deadline = time.time() + 30  # total 30s budget
    while time.time() < deadline:
        if _port_open(host, port, 0.5):
            break
        time.sleep(0.5)
    else:
        pytest.fail(
            f"Postgres not reachable at {host}:{port}. "
            "Start the test DB (see README) or adjust DATABASE_URL.",
        )

    # Now a single quick DB probe
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    if USE_MIGRATIONS:
        _run_migrations()
    else:
        Base.metadata.create_all(bind=engine)

    try:
        yield
    finally:
        if not USE_MIGRATIONS:
            Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def pg_with_secrets_env() -> Iterator[str]:
    """Start ephemeral Postgres and expose credentials via env + password file."""
    with PostgresContainer("postgres:16-alpine") as pg:
        raw_url = pg.get_connection_url().replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        url = make_url(raw_url)

        with tempfile.NamedTemporaryFile("w", delete=False) as pw_file:
            pw_file.write(url.password or "")
            pw_file.flush()
            pw_path = pw_file.name

        os.environ.pop("DATABASE_URL", None)

        os.environ["POSTGRES_HOST"] = url.host or "localhost"
        os.environ["POSTGRES_PORT"] = str(url.port or 5432)
        os.environ["POSTGRES_DB"] = url.database or "postgres"
        os.environ["POSTGRES_USER"] = url.username or "postgres"
        os.environ["POSTGRES_PASSWORD_FILE"] = pw_path

        try:
            yield pw_path
        finally:
            with contextlib.suppress(OSError):
                Path(pw_path).unlink()


@pytest.fixture(scope="session")
def _create_schema(pg_with_secrets_env: str) -> Iterator[None]:
    """Create/drop ORM schema once per session (import after env is set)."""
    del pg_with_secrets_env
    from src.api.core.database import Base, engine

    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=engine)


def test_engine_uses_postgres(pg_with_secrets_env: str) -> None:
    """Engine should be a Postgres engine."""
    del pg_with_secrets_env
    from src.api.core.database import engine

    assert engine.dialect.name == "postgresql"


def test_inet_column_roundtrip(pg_with_secrets_env: str) -> None:
    """Insert and read an INET column to prove driver/type support."""
    del pg_with_secrets_env

    import uuid

    from sqlalchemy.orm import Session

    from src.api.core.database import engine
    from src.api.models.user import User, UserSession

    with Session(engine, future=True) as s:
        u = User(
            id=uuid.uuid4(),
            username="inet_user",
            email="inet@x.test",
            is_active=True,
            is_verified=True,
        )
        s.add(u)
        s.flush()
        token = uuid.uuid4().hex
        sess = UserSession(
            user_id=u.id,
            session_token=token,
            ip_address="2001:db8::1",
        )
        s.add(sess)
        s.commit()

        got = s.query(UserSession).filter_by(session_token=token).first()
        assert got is not None
        assert str(got.ip_address) in {"2001:db8::1", "2001:db8:0:0:0:0:0:1"}
