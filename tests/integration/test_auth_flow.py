"""Comprehensive authentication tests aligned with current routes."""

from __future__ import annotations

import os
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.battleship.core.database import SessionLocal
from src.battleship.main import app
from src.battleship.users.models import AuthService

# --- Constants ---
HTTP_OK = 200
HTTP_SEE_OTHER = 303
TEST_SECRET_KEY = "test-secret-key"  # noqa: S105

# Rate limit skips
SKIP_RATE_LIMIT = pytest.mark.skipif(
    os.environ.get("DISABLE_RATE_LIMIT") == "1",
    reason="Rate limiting disabled in test environment",
)


@pytest.fixture()
def client() -> TestClient:
    # CRITICAL FIX: Provide a valid IP tuple so PostgreSQL INET type doesn't complain.
    # Default is ("testclient", 50000) which fails DB validation.
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture()
def db_session() -> Generator:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def auth_service(db_session) -> AuthService:
    return AuthService(db_session, TEST_SECRET_KEY)


@pytest.fixture()
def sample_user_data() -> dict[str, str]:
    return {
        "email": "test-user@example.com",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!",
    }


# --- Tests ---


class TestUserRegistration:
    def test_successful_registration(
        self, client: TestClient, sample_user_data: dict
    ) -> None:
        # HTMX Response expected
        resp = client.post(
            "/auth/register",
            data=sample_user_data,
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == HTTP_OK
        assert "Account created" in resp.text


class TestUserLogin:
    def test_successful_login(self, client: TestClient, sample_user_data: dict) -> None:
        # 1. Pre-register
        client.post("/auth/register", data=sample_user_data)

        # 2. Login
        resp = client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
            follow_redirects=False,
        )

        # 3. Verify Redirect & Cookies
        assert resp.status_code == HTTP_SEE_OTHER
        assert "session_token" in client.cookies
        assert "access_token" in client.cookies


# --- Unit Tests for Service Logic ---


class TestAuthService:
    @SKIP_RATE_LIMIT
    def test_rate_limiting(self, auth_service: AuthService) -> None:
        """Allow first N actions, then block."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"

        # Assuming limit is 5 for this test context
        for _ in range(5):
            assert (
                auth_service.check_rate_limit(
                    mock_request, "test_action", limit=5, window=60
                )
                is True
            )

        assert (
            auth_service.check_rate_limit(
                mock_request, "test_action", limit=5, window=60
            )
            is False
        )
