"""Integration tests for API endpoints."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from main import app

# pylint: disable=redefined-outer-name


@pytest.fixture()
def client() -> TestClient:
    """Create test client for integration tests."""
    return TestClient(app)


def test_api_integration_health_readiness(client: TestClient) -> None:
    """Health and readiness endpoints work and return expected payloads."""
    health_response = client.get("/health")
    ready_response = client.get("/readyz")

    assert health_response.status_code == HTTPStatus.OK
    assert ready_response.status_code == HTTPStatus.OK

    health_data = health_response.json()
    ready_data = ready_response.json()

    assert health_data["status"] == "ok"
    assert ready_data["status"] == "ready"


def test_all_page_routes_exist(client: TestClient) -> None:
    """Main page routes are accessible (200/500) and not 404."""
    for route in ("/", "/game", "/scores", "/signin", "/signup"):
        resp = client.get(route)
        assert resp.status_code != HTTPStatus.NOT_FOUND, f"Route {route} not found"
