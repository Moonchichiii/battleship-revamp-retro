"""Tests for game routes and HTMX endpoints (updated for refactored game_routes)."""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import patch

import pytest
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from main import app
from src.api.routes.game_routes import get_user_game, reset_user_game

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

ARG_REQUEST_INDEX = 0
ARG_NAME_INDEX = 1
ARG_CONTEXT_INDEX = 2


@pytest.fixture()
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_game_state() -> None:
    """Reset guest game before each test."""
    reset_user_game(user=None, size=DEFAULT_SIZE)


class TestGameHelpers:
    """Game helper tests (guest)."""

    def test_get_user_game_creates_new(self: TestGameHelpers) -> None:
        """Creates a new game."""
        game = get_user_game(user=None, size=DEFAULT_SIZE)
        assert game is not None
        assert game.size == DEFAULT_SIZE

    def test_get_user_game_returns_existing(self: TestGameHelpers) -> None:
        """Returns existing game."""
        game1 = get_user_game(user=None, size=DEFAULT_SIZE)
        game2 = get_user_game(user=None, size=DEFAULT_SIZE)
        assert game1 is game2

    def test_get_user_game_size_change(self: TestGameHelpers) -> None:
        """Size change makes new game."""
        game1 = get_user_game(user=None, size=DEFAULT_SIZE)
        game2 = get_user_game(user=None, size=MIN_SIZE)
        assert game1 is not game2
        assert game2.size == MIN_SIZE

    def test_reset_user_game(self: TestGameHelpers) -> None:
        """Reset returns fresh game."""
        game1 = get_user_game(user=None, size=DEFAULT_SIZE)
        game2 = reset_user_game(user=None, size=DEFAULT_SIZE)
        assert game1 is not game2
        assert game2.size == DEFAULT_SIZE


class TestGameRoutes:
    """Game route endpoint tests (guest)."""

    def test_new_game_endpoint(self: TestGameRoutes, client: TestClient) -> None:
        """POST /new returns HTML."""
        response = client.post("/new", data={"board_size": str(DEFAULT_SIZE)})
        assert response.status_code == HTTPStatus.OK
        assert "text/html" in response.headers["content-type"]

    def test_new_game_custom_size(self: TestGameRoutes, client: TestClient) -> None:
        """Custom size sets board."""
        response = client.post("/new", data={"board_size": str(MAX_SIZE)})
        assert response.status_code == HTTPStatus.OK
        game = get_user_game(user=None, size=MAX_SIZE)
        assert game is not None
        assert game.size == MAX_SIZE

    def test_new_game_size_clamping(self: TestGameRoutes, client: TestClient) -> None:
        """Size is clamped to range."""
        response = client.post("/new", data={"board_size": "3"})
        assert response.status_code == HTTPStatus.OK
        game = get_user_game(user=None, size=MIN_SIZE)
        assert game is not None
        assert game.size == MIN_SIZE

        response = client.post("/new", data={"board_size": "15"})
        assert response.status_code == HTTPStatus.OK
        game = get_user_game(user=None, size=MAX_SIZE)
        assert game is not None
        assert game.size == MAX_SIZE

    def test_new_game_default_size(self: TestGameRoutes, client: TestClient) -> None:
        """Default size used when missing."""
        response = client.post("/new")
        assert response.status_code == HTTPStatus.OK
        game = get_user_game(user=None, size=DEFAULT_SIZE)
        assert game is not None
        assert game.size == DEFAULT_SIZE

    def test_reset_game_endpoint(self: TestGameRoutes, client: TestClient) -> None:
        """POST /reset resets game."""
        initial_game = get_user_game(user=None, size=DEFAULT_SIZE)
        initial_game.fire(0, 0)

        response = client.post("/reset", data={"board_size": str(DEFAULT_SIZE)})
        assert response.status_code == HTTPStatus.OK

        new_game = get_user_game(user=None, size=DEFAULT_SIZE)
        assert new_game is not None
        assert new_game is not initial_game
        assert new_game.size == DEFAULT_SIZE

    def test_reset_game_custom_size(self: TestGameRoutes, client: TestClient) -> None:
        """Reset with custom size."""
        get_user_game(user=None, size=MIN_SIZE)
        response = client.post("/reset", data={"board_size": str(CUSTOM_SIZE)})
        assert response.status_code == HTTPStatus.OK
        game = get_user_game(user=None, size=CUSTOM_SIZE)
        assert game is not None
        assert game.size == CUSTOM_SIZE

    def test_shot_endpoint_valid(self: TestGameRoutes, client: TestClient) -> None:
        """Valid shot registers."""
        response = client.post("/shot/3/4", data={"board_size": str(DEFAULT_SIZE)})
        assert response.status_code == HTTPStatus.OK
        game = get_user_game(user=None, size=DEFAULT_SIZE)
        assert game is not None
        assert (3, 4) in game.hits or (3, 4) in game.misses

    def test_shot_endpoint_boundary(self: TestGameRoutes, client: TestClient) -> None:
        """Corner shots accepted."""
        get_user_game(user=None, size=DEFAULT_SIZE)
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
        """Out-of-bounds shots ignored."""
        get_user_game(user=None, size=DEFAULT_SIZE)
        response = client.post("/shot/10/10", data={"board_size": str(DEFAULT_SIZE)})
        assert response.status_code == HTTPStatus.OK
        game = get_user_game(user=None, size=DEFAULT_SIZE)
        assert game is not None
        assert (10, 10) not in game.hits
        assert (10, 10) not in game.misses

    def test_shot_endpoint_negative_coords(
        self: TestGameRoutes,
        client: TestClient,
    ) -> None:
        """Negative coords handled or rejected."""
        get_user_game(user=None, size=DEFAULT_SIZE)

        resp = client.post("/shot/-1/-1", data={"board_size": str(DEFAULT_SIZE)})

        if resp.status_code == HTTPStatus.OK:
            game = get_user_game(user=None, size=DEFAULT_SIZE)
            assert game is not None
            assert (-1, -1) not in game.hits
            assert (-1, -1) not in game.misses
        else:
            assert resp.status_code == HTTPStatus.NOT_FOUND

    def test_shot_endpoint_size_mismatch(
        self: TestGameRoutes,
        client: TestClient,
    ) -> None:
        """Different size makes new game."""
        game = get_user_game(user=None, size=DEFAULT_SIZE)
        original_id = id(game)
        response = client.post(
            f"/shot/{TEST_COORD}/{TEST_COORD}",
            data={"board_size": str(MIN_SIZE)},
        )
        assert response.status_code == HTTPStatus.OK
        new_game = get_user_game(user=None, size=MIN_SIZE)
        assert new_game is not None
        assert id(new_game) != original_id
        assert new_game.size == MIN_SIZE

    def test_game_status_endpoint(self: TestGameRoutes, client: TestClient) -> None:
        """GET /game-status returns HTML."""
        game = get_user_game(user=None, size=DEFAULT_SIZE)
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
        """Template receives expected fields."""
        with patch(
            "src.api.routes.game_routes.templates.TemplateResponse",
        ) as mock_template:
            mock_template.return_value = HTMLResponse("<div>ok</div>")

            game = reset_user_game(user=None, size=MIN_SIZE)
            game.ships = {(0, 0), (1, 1), (2, 2)}
            game.fire(0, 0)
            game.fire(5, 5)

            with patch(
                "src.api.routes.game_routes.get_user_game",
                return_value=game,
            ):
                client.get(f"/game-status?ai_tier=rookie&size={MIN_SIZE}")

        mock_template.assert_called_once()
        args, kwargs = mock_template.call_args

        template_name = (
            args[ARG_NAME_INDEX] if len(args) > ARG_NAME_INDEX else kwargs.get("name")
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
        """Accuracy calculation is correct."""
        with patch(
            "src.api.routes.game_routes.templates.TemplateResponse",
        ) as mock_template:
            mock_template.return_value = HTMLResponse("<div>ok</div>")

            game = get_user_game(user=None, size=DEFAULT_SIZE)
            game.hits.clear()
            game.misses.clear()

            hits_count = HITS_COUNT
            misses_count = MISSES_COUNT
            expected_shots = hits_count + misses_count
            expected_accuracy = round(hits_count / expected_shots * 100, 1)

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
        """No shots => zeros."""
        with patch(
            "src.api.routes.game_routes.templates.TemplateResponse",
        ) as mock_template:
            mock_template.return_value = HTMLResponse("<div>ok</div>")

            get_user_game(user=None, size=DEFAULT_SIZE)
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
            assert status["accuracy"] == 0.0
