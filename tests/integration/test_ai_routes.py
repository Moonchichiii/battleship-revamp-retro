"""Integration tests for AI routes (HTMX fragments, auth required)."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from src.battleship.main import app

if TYPE_CHECKING:
    pass

HTTP_OK = 200
HTTP_NOT_FOUND = 404

@dataclass(slots=True, frozen=True)
class _User:
    id: str
    username: str
    email: str = "test@example.com"
    display_name: str = "Tester"
    avatar_url: str = None
    is_active: bool = True
    is_verified: bool = True
    permissions: list = None

@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)

@pytest.fixture(autouse=True)
def _cleanup_sessions() -> Generator[None, None, None]:
    yield
    from src.battleship.api.routes.ai import _SESSIONS
    _SESSIONS.clear()

@pytest.fixture(autouse=True)
def _override_auth_dependency() -> Generator[None, None, None]:
    """Fake an authenticated user."""
    from src.battleship.users.models import require_authenticated_user

    def _fake_auth_user() -> _User:
        return _User(id="u-1", username="tester")

    app.dependency_overrides[require_authenticated_user] = _fake_auth_user
    yield
    app.dependency_overrides.pop(require_authenticated_user, None)

def test_ai_lobby_requires_auth(client: TestClient) -> None:
    r = client.get("/ai", headers={"HX-Request": "true"})
    assert r.status_code == HTTP_OK
    assert "AI Opponents" in r.text

@pytest.mark.parametrize(
    ("tier", "size"),
    [("rookie", 6), ("veteran", 8), ("admiral", 10)],
)
def test_start_game_valid_tiers(client: TestClient, tier: str, size: int) -> None:
    r = client.post("/ai/start", data={"tier": tier})
    assert r.status_code == HTTP_OK
    assert f"AI: {tier.title()}" in r.text

def test_start_game_invalid_tier(client: TestClient) -> None:
    r = client.post("/ai/start", data={"tier": "unknown"})
    assert r.status_code == HTTP_NOT_FOUND
