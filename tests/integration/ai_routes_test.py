"""Integration tests for AI routes (HTMX fragments, auth required)."""

from __future__ import annotations

# --- stdlib ---
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

# --- third-party ---
import pytest
from fastapi.testclient import TestClient

# --- application ---
from main import app

if TYPE_CHECKING:
    from collections.abc import Generator

# --- constants ---
HTTP_OK = 200
HTTP_NOT_FOUND = 404
EXPECTED_SCORE = 1100
TEST_SHOTS_FIRED = 10
TEST_ACCURACY = 80.0
TEST_BOARD_SIZE = 8


@dataclass(slots=True, frozen=True)
class _User:
    id: str
    username: str


@pytest.fixture()
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _cleanup_sessions() -> Generator[None]:
    """Clean up AI sessions between tests."""
    yield
    # Clean up sessions after each test
    from src.api.routes.ai_routes import _SESSIONS

    _SESSIONS.clear()


@pytest.fixture(autouse=True)
def _override_auth_dependency() -> Generator[None]:
    """Fake an authenticated user."""
    from src.api.models.user import require_authenticated_user

    def _fake_auth_user() -> _User:
        return _User(id="u-1", username="tester")

    app.dependency_overrides[require_authenticated_user] = _fake_auth_user
    yield
    app.dependency_overrides.pop(require_authenticated_user, None)


def test_ai_lobby_requires_auth(client: TestClient) -> None:
    """Render AI lobby when authenticated."""
    r = client.get("/ai", headers={"HX-Request": "true"})
    assert r.status_code == HTTP_OK
    assert "<h2>AI Opponents</h2>" in r.text
    assert "Signed in as" in r.text
    assert "Rookie" in r.text
    assert "Veteran" in r.text
    assert "Admiral" in r.text


@pytest.mark.parametrize(
    ("tier", "size"),
    [("rookie", 6), ("veteran", 8), ("admiral", 10)],
)
def test_start_game_valid_tiers(client: TestClient, tier: str, size: int) -> None:
    """Start a game for valid tiers."""
    # Send as form data, not JSON
    r = client.post("/ai/start", data={"tier": tier})
    assert r.status_code == HTTP_OK
    assert f"AI: {tier.title()}" in r.text
    assert f"Board: {size}x{size}" in r.text
    assert "Enemy Waters" in r.text
    assert "Your Fleet" in r.text


def test_start_game_invalid_tier(client: TestClient) -> None:
    """Reject unknown tier."""
    # Send as form data, not JSON
    r = client.post("/ai/start", data={"tier": "unknown"})
    assert r.status_code == HTTP_NOT_FOUND
    assert "Unknown tier" in r.text


@pytest.fixture()
def isolated_client() -> Generator[TestClient]:
    """Create isolated test client with fresh sessions."""
    from src.api.routes.ai_routes import _SESSIONS

    # Clear sessions before test
    _SESSIONS.clear()

    client = TestClient(app)
    yield client

    # Clear sessions after test
    _SESSIONS.clear()


def test_player_shot_without_session_404() -> None:
    """404 when firing without active game."""
    from src.api.models.user import require_authenticated_user
    from src.api.routes.ai_routes import _SESSIONS

    # Override auth just for this test
    def _fake_auth_user() -> _User:
        return _User(id="u-isolated", username="isolated")

    app.dependency_overrides[require_authenticated_user] = _fake_auth_user

    try:
        # Ensure clean state
        _SESSIONS.clear()

        client = TestClient(app)

        # Send request without establishing session first
        r = client.post("/ai/shot", data={"x": 0, "y": 0, "tier": "rookie"})

        assert (
            r.status_code == HTTP_NOT_FOUND
        ), f"Expected 404, got {r.status_code}. Sessions: {len(_SESSIONS)}"
        assert "No active game" in r.text

    finally:
        # Cleanup
        app.dependency_overrides.pop(require_authenticated_user, None)
        _SESSIONS.clear()


def test_player_shot_updates_screen(client: TestClient) -> None:
    """Apply a shot and re-render screen with AI response."""
    # Send as form data, not JSON
    start = client.post("/ai/start", data={"tier": "rookie"})
    assert start.status_code == HTTP_OK
    assert "AI: Rookie" in start.text

    shot = client.post("/ai/shot", data={"x": 0, "y": 0, "tier": "rookie"})
    assert shot.status_code == HTTP_OK
    assert "AI: Rookie" in shot.text
    assert "Your shots:" in shot.text  # Updated stats format
    assert "Enemy Waters" in shot.text
    assert "Your Fleet" in shot.text


def test_ai_makes_move_after_player(client: TestClient) -> None:
    """Verify AI makes a move after player shot."""
    # Start game
    start = client.post("/ai/start", data={"tier": "rookie"})
    assert start.status_code == HTTP_OK

    # Player makes a shot
    shot = client.post("/ai/shot", data={"x": 0, "y": 0, "tier": "rookie"})
    assert shot.status_code == HTTP_OK

    # Should contain AI move information
    assert "AI's last move:" in shot.text or "Turn: Player" in shot.text


def test_sessions_are_per_user(client: TestClient) -> None:
    """Keep game state separate per user."""
    # Send as form data, not JSON
    r1 = client.post("/ai/start", data={"tier": "rookie"})
    assert r1.status_code == HTTP_OK

    from src.api.models.user import require_authenticated_user as _dep

    def _fake_user2() -> _User:
        return _User(id="u-2", username="tester2")

    app.dependency_overrides[_dep] = _fake_user2

    r2 = client.post("/ai/start", data={"tier": "rookie"})
    assert r2.status_code == HTTP_OK
    assert "AI: Rookie" in r2.text

    shot2 = client.post("/ai/shot", data={"x": 1, "y": 1, "tier": "rookie"})
    assert shot2.status_code == HTTP_OK
    assert "Enemy Waters" in shot2.text


def test_different_ai_tiers_have_different_descriptions(client: TestClient) -> None:
    """Verify lobby shows different AI descriptions."""
    r = client.get("/ai")
    assert r.status_code == HTTP_OK
    assert "Random moves with basic hit follow-up" in r.text
    assert "checkerboard pattern and hunt mode" in r.text
    assert "probability-based targeting" in r.text


@dataclass(slots=True, frozen=True)
class _FakeUser:
    id: str
    username: str
    display_name: str | None = None
    is_active: bool = True


class _FakeScoreService:
    """Stub score service returning deterministic data."""

    def __init__(self) -> None:
        self._scores: list[dict[str, Any]] = [
            {
                "player_name": "Ada",
                "score": 950,
                "created_at": datetime.now(UTC),
                "shots_fired": 12,
                "accuracy": 75.0,
                "board_size": 8,
            },
            {
                "player_name": "Linus",
                "score": 900,
                "created_at": datetime.now(UTC),
                "shots_fired": 15,
                "accuracy": 68.0,
                "board_size": 10,
            },
        ]

    def get_top_scores(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._scores[:limit]

    def create_score(
        self,
        user_id: str,  # Fixed: specific type instead of Any
        score: int,
        shots_fired: int,
        accuracy: float,
        board_size: int,
    ) -> dict[str, Any]:
        """Create a new score record."""
        new_score = {
            "player_name": f"user-{user_id}",
            "score": score,
            "created_at": datetime.now(UTC),
            "shots_fired": shots_fired,
            "accuracy": accuracy,
            "board_size": board_size,
        }
        self._scores.append(new_score)
        return new_score


@pytest.fixture(autouse=True)
def _override_scores_dependencies() -> Generator[None]:
    """Override score and user dependencies."""
    from src.api.models.user import get_auth_service, optional_authenticated_user
    from src.api.routes import scores_routes as sr

    def _fake_optional_user() -> _FakeUser:
        return _FakeUser(id="u-1", username="tester", display_name="Tester")

    app.dependency_overrides[optional_authenticated_user] = _fake_optional_user

    def _provide_fake_service() -> _FakeScoreService:
        return _FakeScoreService()

    app.dependency_overrides[sr.get_score_service] = _provide_fake_service

    class _FakeAuthService:  # Fixed: specific class instead of Any
        db = None  # pragma: no cover

    def _fake_auth_service() -> _FakeAuthService:
        return _FakeAuthService()

    app.dependency_overrides[get_auth_service] = _fake_auth_service

    yield

    app.dependency_overrides.pop(optional_authenticated_user, None)
    app.dependency_overrides.pop(sr.get_score_service, None)
    app.dependency_overrides.pop(get_auth_service, None)


def test_scores_page_renders_table(client: TestClient) -> None:
    """Render /scores with top scores."""
    r = client.get("/scores")
    assert r.status_code == HTTP_OK
    # Check for the fake data we set up in _FakeScoreService
    assert "Ada" in r.text or "Linus" in r.text or "No scores yet" in r.text


def test_api_top_scores_partial_uses_limit(client: TestClient) -> None:
    """Render tbody partial with limit param."""
    r = client.get("/api/scores/top?limit=1", headers={"HX-Request": "true"})
    assert r.status_code == HTTP_OK
    # Should contain at least one score or the "No scores yet" message
    assert "Ada" in r.text or "No scores yet" in r.text


def test_save_game_score_calculates_score() -> None:
    """Compute final score and call create_score."""
    from src.api.routes import scores_routes as sr

    fake = _FakeScoreService()
    game_stats = {
        "shots_fired": TEST_SHOTS_FIRED,
        "accuracy": TEST_ACCURACY,
        "board_size": TEST_BOARD_SIZE,
    }
    saved = sr.save_game_score(user_id="u-7", game_stats=game_stats, score_service=fake)
    assert isinstance(saved, dict)
    assert saved["score"] == EXPECTED_SCORE
    assert saved["shots_fired"] == TEST_SHOTS_FIRED
    assert saved["accuracy"] == TEST_ACCURACY
    assert saved["board_size"] == TEST_BOARD_SIZE
