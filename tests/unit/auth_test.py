"""Unit tests for authentication endpoints (validation & pages)."""

from __future__ import annotations

from http import HTTPStatus

from fastapi.testclient import TestClient

from main import app


def _client() -> TestClient:
    return TestClient(app)


def test_sign_pages_exist() -> None:
    """Sign-in and sign-up pages render (not 404)."""
    client = _client()
    for route in ("/signin", "/signup"):
        resp = client.get(route)
        assert resp.status_code != HTTPStatus.NOT_FOUND, f"{route} not found"


def test_register_requires_fields() -> None:
    """POST /auth/register requires form fields (422)."""
    client = _client()
    resp = client.post("/auth/register", data={})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_login_requires_fields() -> None:
    """POST /auth/login requires form fields (422)."""
    client = _client()
    resp = client.post("/auth/login", data={})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
