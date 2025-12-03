"""Tests for game routes and HTMX endpoints."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from src.battleship.api.routes.game import _SESSIONS
from src.battleship.main import app

DEFAULT_SIZE = 8


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_game_state() -> None:
    _SESSIONS.clear()


class TestGameRoutes:
    def test_new_game_endpoint(self, client: TestClient) -> None:
        response = client.post("/new", data={"ai_tier": "rookie"})
        assert response.status_code == HTTPStatus.OK
        assert "text/html" in response.headers["content-type"]

    def test_make_move_endpoint(self, client: TestClient) -> None:
        client.post("/new")

        response = client.post("/make-move", data={"x": 0, "y": 0, "ai_tier": "rookie"})
        assert response.status_code == HTTPStatus.OK
        assert "board-container" in response.text
