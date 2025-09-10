"""Tests for game routes and HTMX endpoints."""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import patch

import pytest
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from main import app
from src.api.routes.game_routes import _STATE, get_current_game, reset_current_game

# Constants
DEFAULT_SIZE = 8
MIN_SIZE = 6
MAX_SIZE = 10
CUSTOM_SIZE = 9
EXPECTED_SHOTS_MIN = 2
HITS_COUNT = 2
MISSES_COUNT = 4

TEST_COORD = 2
HIT_COORDS = [(0, 0), (1, 1)]
MISS_COORDS = [(2, 2), (3, 3), (4, 4), (5, 5)]

ARG_NAME_INDEX = 1
ARG_CONTEXT_INDEX = 2


@pytest.fixture()
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_game_state() -> None:
    """Reset global game state before each test."""
    _STATE["game"] = None
    _STATE["size"] = DEFAULT_SIZE


class TestGameHelpers:
    """Test game helper functions."""

    def test_get_current_game_creates_new(self: TestGameHelpers) -> None:
        """get_current_game creates a new game when none exists."""
        game = get_current_game(size=DEFAULT_SIZE)

        assert game is not None
        assert game.size == DEFAULT_SIZE
        assert _STATE["game"] == game
        assert _STATE["size"] == DEFAULT_SIZE

    def test_get_current_game_returns_existing(self: TestGameHelpers) -> None:
        """get_current_game returns the existing game instance."""
        game1 = get_current_game(size=DEFAULT_SIZE)
        game2 = get_current_game(size=DEFAULT_SIZE)
        assert game1 is game2

    def test_get_current_game_size_change(self: TestGameHelpers) -> None:
        """A size change creates a new game instance."""
        game1 = get_current_game(size=DEFAULT_SIZE)
        game2 = get_current_game(size=MIN_SIZE)
        assert game1 is not game2
        assert game2.size == MIN_SIZE

    def test_reset_current_game(self: TestGameHelpers) -> None:
        """reset_current_game returns a fresh game instance."""
        game1 = get_current_game(size=DEFAULT_SIZE)
        game2 = reset_current_game(size=DEFAULT_SIZE)
        assert game1 is not game2
        assert game2.size == DEFAULT_SIZE
        assert _STATE["game"] == game2


class TestGameRoutes:
    """Test game route endpoints."""

    def test_new_game_endpoint(self: TestGameRoutes, client: TestClient) -> None:
        """POST /new creates a new game and returns HTML."""
        response = client.post("/new", data={"board_size": str(DEFAULT_SIZE)})
        assert response.status_code == HTTPStatus.OK
        assert "text/html" in response.headers["content-type"]

    def test_new_game_custom_size(self: TestGameRoutes, client: TestClient) -> None:
        """POST /new with custom board size sets the size correctly."""
        response = client.post("/new", data={"board_size": str(MAX_SIZE)})
        assert response.status_code == HTTPStatus.OK
        game = _STATE["game"]
        assert game is not None
        assert game.size == MAX_SIZE

    def test_new_game_size_clamping(self: TestGameRoutes, client: TestClient) -> None:
        """POST /new clamps board size to valid range."""
        response = client.post("/new", data={"board_size": str(3)})
        assert response.status_code == HTTPStatus.OK
        game = _STATE["game"]
        assert game is not None
        assert game.size == MIN_SIZE

        response = client.post("/new", data={"board_size": str(15)})
        assert response.status_code == HTTPStatus.OK
        game = _STATE["game"]
        assert game is not None
        assert game.size == MAX_SIZE

    def test_new_game_default_size(self: TestGameRoutes, client: TestClient) -> None:
        """POST /new without size uses the default."""
        response = client.post("/new")
        assert response.status_code == HTTPStatus.OK
        game = _STATE["game"]
        assert game is not None
        assert game.size == DEFAULT_SIZE

    def test_reset_game_endpoint(self: TestGameRoutes, client: TestClient) -> None:
        """POST /reset resets the current game."""
        initial_game = get_current_game(size=DEFAULT_SIZE)
        initial_game.fire(0, 0)

        response = client.post("/reset", data={"board_size": str(DEFAULT_SIZE)})
        assert response.status_code == HTTPStatus.OK

        new_game = _STATE["game"]
        assert new_game is not None
        assert new_game is not initial_game
        assert new_game.size == DEFAULT_SIZE

    def test_reset_game_custom_size(self: TestGameRoutes, client: TestClient) -> None:
        """POST /reset with custom size sets the size."""
        get_current_game(size=MIN_SIZE)
        response = client.post("/reset", data={"board_size": str(CUSTOM_SIZE)})
        assert response.status_code == HTTPStatus.OK
        game = _STATE["game"]
        assert game is not None
        assert game.size == CUSTOM_SIZE

    def test_shot_endpoint_valid(self: TestGameRoutes, client: TestClient) -> None:
        """POST /shot/{x}/{y} registers a shot for valid coords."""
        response = client.post("/shot/3/4", data={"board_size": str(DEFAULT_SIZE)})
        assert response.status_code == HTTPStatus.OK
        game = _STATE["game"]
        assert game is not None
        assert (3, 4) in game.hits or (3, 4) in game.misses

    def test_shot_endpoint_boundary(self: TestGameRoutes, client: TestClient) -> None:
        """Shots at board corners are accepted."""
        get_current_game(size=DEFAULT_SIZE)
        corners = [
            (0, 0),
            (DEFAULT_SIZE - 1, DEFAULT_SIZE - 1),
            (0, DEFAULT_SIZE - 1),
            (DEFAULT_SIZE - 1, 0),
        ]
        for x, y in corners:
            response = client.post(
                f"/shot/{x}/{y}",
                data={"board_size": str(DEFAULT_SIZE)},
            )
            assert response.status_code == HTTPStatus.OK

    def test_shot_endpoint_out_of_bounds(
        self: TestGameRoutes,
        client: TestClient,
    ) -> None:
        """Out-of-bounds shots do not register and do not crash."""
        get_current_game(size=DEFAULT_SIZE)
        response = client.post("/shot/10/10", data={"board_size": str(DEFAULT_SIZE)})
        assert response.status_code == HTTPStatus.OK
        game = _STATE["game"]
        assert game is not None
        assert (10, 10) not in game.hits
        assert (10, 10) not in game.misses

    def test_shot_endpoint_negative_coords(
        self: TestGameRoutes,
        client: TestClient,
    ) -> None:
        """Negative coordinates return 404 (router int converter)."""
        get_current_game(size=DEFAULT_SIZE)
        resp = client.post("/shot/-1/-1", data={"board_size": str(DEFAULT_SIZE)})
        assert resp.status_code == HTTPStatus.NOT_FOUND
        game = _STATE["game"]
        assert game is not None
        assert (-1, -1) not in game.hits
        assert (-1, -1) not in game.misses

    def test_shot_endpoint_size_mismatch(
        self: TestGameRoutes,
        client: TestClient,
    ) -> None:
        """Providing a different board_size creates a new game instance."""
        game = get_current_game(size=DEFAULT_SIZE)
        original_id = id(game)
        response = client.post(
            f"/shot/{TEST_COORD}/{TEST_COORD}",
            data={"board_size": str(MIN_SIZE)},
        )
        assert response.status_code == HTTPStatus.OK
        new_game = _STATE["game"]
        assert new_game is not None
        assert id(new_game) != original_id
        assert new_game.size == MIN_SIZE

    def test_game_status_endpoint(self: TestGameRoutes, client: TestClient) -> None:
        """GET /game-status returns HTML and 200."""
        game = get_current_game(size=DEFAULT_SIZE)
        game.fire(0, 0)
        game.fire(1, 1)
        with patch(
            "src.api.routes.game_routes.templates.TemplateResponse",
        ) as mock_tpl:
            mock_tpl.return_value = HTMLResponse("<div>ok</div>")
            resp = client.get("/game-status")
        assert resp.status_code == HTTPStatus.OK
        assert "text/html" in resp.headers["content-type"]

    def test_game_status_template_data(
        self: TestGameRoutes,
        client: TestClient,
    ) -> None:
        """Template receives expected status context fields/values."""
        with patch(
            "src.api.routes.game_routes.templates.TemplateResponse",
        ) as mock_template:
            mock_template.return_value = HTMLResponse("<div>ok</div>")

            game = get_current_game(size=MIN_SIZE)
            game.ships = {(0, 0), (1, 1), (2, 2)}
            game.fire(0, 0)  # hit
            game.fire(5, 5)  # miss

            client.get("/game-status")

            mock_template.assert_called_once()
            args, kwargs = mock_template.call_args
            template_name = (
                args[ARG_NAME_INDEX]
                if len(args) > ARG_NAME_INDEX
                else kwargs.get("name")
            )
            context = (
                args[ARG_CONTEXT_INDEX]
                if len(args) > ARG_CONTEXT_INDEX
                else kwargs.get("context", {})
            )
            status = context["status"]

            assert template_name == "_game_status.html"
            assert status["board_size"] == MIN_SIZE
            assert status["total_cells"] == MIN_SIZE * MIN_SIZE
            assert status["shots_fired"] >= EXPECTED_SHOTS_MIN
            assert status["hits"] >= 1

    def test_game_status_accuracy_calculation(
        self: TestGameRoutes,
        client: TestClient,
    ) -> None:
        """Accuracy = round(hits / (hits+misses) * 100)."""
        with patch(
            "src.api.routes.game_routes.templates.TemplateResponse",
        ) as mock_template:
            mock_template.return_value = HTMLResponse("<div>ok</div>")

            game = get_current_game(size=DEFAULT_SIZE)
            game.hits.clear()
            game.misses.clear()

            hits_count = HITS_COUNT
            misses_count = MISSES_COUNT
            expected_shots = hits_count + misses_count
            expected_accuracy = round(hits_count / expected_shots * 100)

            game.hits.update(HIT_COORDS)
            game.misses.update(MISS_COORDS)

            client.get("/game-status")

            args, kwargs = mock_template.call_args
            context = (
                args[ARG_CONTEXT_INDEX]
                if len(args) > ARG_CONTEXT_INDEX
                else kwargs.get("context", {})
            )
            status = context["status"]
            assert status["shots_fired"] == expected_shots
            assert status["hits"] == hits_count
            assert status["accuracy"] == expected_accuracy

    def test_game_status_no_shots_fired(
        self: TestGameRoutes,
        client: TestClient,
    ) -> None:
        """No shots => 0 shots_fired, 0 hits, 0 accuracy."""
        with patch(
            "src.api.routes.game_routes.templates.TemplateResponse",
        ) as mock_template:
            mock_template.return_value = HTMLResponse("<div>ok</div>")

            get_current_game(size=DEFAULT_SIZE)
            client.get("/game-status")

            args, kwargs = mock_template.call_args
            context = (
                args[ARG_CONTEXT_INDEX]
                if len(args) > ARG_CONTEXT_INDEX
                else kwargs.get("context", {})
            )
            status = context["status"]
            assert status["shots_fired"] == 0
            assert status["hits"] == 0
            assert status["accuracy"] == 0
