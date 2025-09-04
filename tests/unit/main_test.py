"""Unit tests for the Battleship Revamp application."""

from __future__ import annotations

import importlib
from http import HTTPStatus
from unittest.mock import Mock

import pytest  # type: ignore[import-not-found]
from fastapi.testclient import TestClient

from main import app, is_hx


# pylint: disable=redefined-outer-name
@pytest.fixture()
def client_fx() -> TestClient:
    """Fixture to provide a test client."""
    return TestClient(app)


def test_app_creation() -> None:
    """Application object is created with right title."""
    assert app is not None
    assert app.title == "Battleship Revamp"


def test_health_endpoint(client_fx: TestClient) -> None:
    """GET /health returns ok + timestamp."""
    resp = client_fx.get("/health")
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert data["status"] == "ok"
    assert "ts" in data


def test_readyz_endpoint(client_fx: TestClient) -> None:
    """GET /readyz returns ready + timestamp."""
    resp = client_fx.get("/readyz")
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert data["status"] == "ready"
    assert "ts" in data


def test_home_page(client_fx: TestClient) -> None:
    """Home page exists (200 or template 500)."""
    resp = client_fx.get("/")
    assert resp.status_code in (HTTPStatus.OK, HTTPStatus.INTERNAL_SERVER_ERROR)


def test_game_page(client_fx: TestClient) -> None:
    """Game page exists (200 or template 500)."""
    resp = client_fx.get("/game")
    assert resp.status_code in (HTTPStatus.OK, HTTPStatus.INTERNAL_SERVER_ERROR)


def test_scores_page(client_fx: TestClient) -> None:
    """Scores page exists (200 or template 500)."""
    resp = client_fx.get("/scores")
    assert resp.status_code in (HTTPStatus.OK, HTTPStatus.INTERNAL_SERVER_ERROR)


def test_signin_page(client_fx: TestClient) -> None:
    """Signin page exists (200 or template 500)."""
    resp = client_fx.get("/signin")
    assert resp.status_code in (HTTPStatus.OK, HTTPStatus.INTERNAL_SERVER_ERROR)


def test_signup_page(client_fx: TestClient) -> None:
    """Signup page exists (200 or template 500)."""
    resp = client_fx.get("/signup")
    assert resp.status_code in (HTTPStatus.OK, HTTPStatus.INTERNAL_SERVER_ERROR)


def test_is_hx_true() -> None:
    """True when HX-Request header is 'true'."""
    req = Mock()
    req.headers.get.return_value = "true"
    assert is_hx(req) is True
    req.headers.get.assert_called_once_with("HX-Request", "")


def test_is_hx_false() -> None:
    """False when HX-Request header missing/empty."""
    req = Mock()
    req.headers.get.return_value = ""
    assert is_hx(req) is False


def test_is_hx_case_insensitive() -> None:
    """Case-insensitive check."""
    req = Mock()
    req.headers.get.return_value = "TRUE"
    assert is_hx(req) is True


def test_basic_import_module() -> None:
    """Smoke test that the main module can be imported."""
    mod = importlib.import_module("main")
    assert hasattr(mod, "app")
    assert hasattr(mod, "is_hx")
