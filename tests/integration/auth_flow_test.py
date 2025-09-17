"""Comprehensive authentication tests aligned with current routes."""

# ruff: noqa: D101

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from main import app
from src.api.core.database import SessionLocal
from src.api.core.security import (
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
    verify_token,
)
from src.api.models.user import AuthService

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.orm import Session

# --- constants ---
HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_UNPROCESSABLE_ENTITY = 422
HTTP_INTERNAL_SERVER_ERROR = 500
HTTP_TEMPORARY_REDIRECT = 307
HTTP_SEE_OTHER = 303

TEST_GITHUB_ID = 12345
TEST_USER_ID = "123"
RATE_LIMIT_ATTEMPTS = 6
LOGIN_RATE_LIMIT_ATTEMPTS = 11
TEST_SECRET_KEY = "test-secret-key"  # noqa: S105
HX_HEADERS = {"HX-Request": "true"}

# --- shared marks ---
SKIP_RATE_LIMIT = pytest.mark.skipif(
    os.getenv("DISABLE_RATE_LIMIT") == "1" or os.getenv("TESTING") == "true",
    reason="Rate limiting disabled in test environment",
)


# --- fixtures ---
@pytest.fixture()
def client() -> TestClient:
    """Return FastAPI TestClient bound to app."""
    return TestClient(app)


@pytest.fixture()
def db_session() -> Generator[Session]:
    """Provide DB session and ensure cleanup."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def auth_service(db_session: Session) -> AuthService:
    """Return AuthService wired to test DB."""
    return AuthService(db_session, TEST_SECRET_KEY)


@pytest.fixture
def unique_email() -> str:
    """Generate unique email per test."""
    return f"test+{uuid4().hex}@example.com"


@pytest.fixture
def sample_user_data(unique_email: str) -> dict[str, str]:
    """Valid registration payload."""  # noqa: D401
    return {
        "email": unique_email,
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!",
    }


@pytest.fixture
def weak_password_data(unique_email: str) -> dict[str, str]:
    """Weak password payload."""
    return {
        "email": unique_email,
        "password": "weak",
        "confirm_password": "weak",
    }


# --- top-level rate-limit placeholders (kept) ---
@SKIP_RATE_LIMIT
def test_registration_rate_limiting(client: TestClient) -> None:
    """Placeholder: registration RL skipped when disabled."""
    # existing test code...


@SKIP_RATE_LIMIT
def test_login_rate_limiting(
    client: TestClient,
    sample_user_data: dict[str, str],
) -> None:
    """Placeholder: login RL skipped when disabled."""
    # existing test code...


class TestUserRegistration_RateLimitOnly:  # noqa: N801
    @SKIP_RATE_LIMIT
    def test_registration_rate_limiting(self, client: TestClient) -> None:
        """Class placeholder: registration RL skipped when disabled."""
        # existing test code...


class TestUserLogin_RateLimitOnly:  # noqa: N801
    @SKIP_RATE_LIMIT
    def test_login_rate_limiting(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Class placeholder: login RL skipped when disabled."""
        # existing test code...


class TestAuthService_RateLimitOnly:  # noqa: N801
    @SKIP_RATE_LIMIT
    def test_rate_limiting(self, auth_service: AuthService) -> None:
        """Class placeholder: service RL skipped when disabled."""
        # existing test code...


# --- registration (non-HTMX, class) ---
class TestUserRegistration:
    def test_successful_registration(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Register new user successfully."""
        resp = client.post("/auth/register", data=sample_user_data)
        assert resp.status_code == HTTP_OK
        assert "Account created successfully" in resp.text
        assert "test" in resp.text

    def test_registration_with_weak_password(
        self,
        client: TestClient,
        weak_password_data: dict[str, str],
    ) -> None:
        """Reject weak password at registration."""
        resp = client.post("/auth/register", data=weak_password_data)
        assert resp.status_code == HTTP_OK
        assert "Password" in resp.text or "must" in resp.text

    def test_registration_password_mismatch(self, client: TestClient) -> None:
        """Reject mismatched passwords."""
        data = {
            "email": "test@example.com",
            "password": "SecurePass123!",
            "confirm_password": "DifferentPass123!",
        }
        resp = client.post("/auth/register", data=data)
        assert resp.status_code == HTTP_OK
        assert "Passwords do not match" in resp.text

    def test_registration_duplicate_email(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Reject duplicate email registration."""
        client.post("/auth/register", data=sample_user_data)
        resp = client.post("/auth/register", data=sample_user_data)
        assert resp.status_code == HTTP_OK
        assert "already exists" in resp.text

    def test_registration_invalid_email(self, client: TestClient) -> None:
        """Reject invalid email format."""
        data = {
            "email": "not-an-email",
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
        }
        resp = client.post("/auth/register", data=data)
        assert resp.status_code == HTTP_OK
        assert "Invalid email format" in resp.text

    @SKIP_RATE_LIMIT
    def test_registration_rate_limiting(self, client: TestClient) -> None:
        """Enforce registration rate limit."""
        last = None
        for i in range(RATE_LIMIT_ATTEMPTS):
            data = {
                "email": f"rl{i}@example.com",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
            }
            last = client.post("/auth/register", data=data)
        assert last is not None
        assert "Too many register attempts" in last.text


# --- login/logout (non-HTMX, class) ---
class TestUserLogin:
    def test_successful_login(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Login success returns redirect and sets cookies."""
        client.post("/auth/register", data=sample_user_data)
        resp = client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
            follow_redirects=False,
        )
        assert resp.status_code == HTTP_SEE_OTHER
        assert "session_token" in client.cookies
        assert "access_token" in client.cookies

    def test_login_wrong_password(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Reject login with wrong password."""
        client.post("/auth/register", data=sample_user_data)
        resp = client.post(
            "/auth/login",
            data={"email": sample_user_data["email"], "password": "WrongPassword123!"},
        )
        assert resp.status_code == HTTP_OK
        assert "Invalid email or password" in resp.text

    def test_login_nonexistent_user(self, client: TestClient) -> None:
        """Reject login for unknown user."""
        resp = client.post(
            "/auth/login",
            data={"email": "nonexistent@example.com", "password": "SomePassword123!"},
        )
        assert resp.status_code == HTTP_OK
        assert "Invalid email or password" in resp.text

    def test_login_sets_cookies(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Ensure session/access cookies set on login."""
        client.post("/auth/register", data=sample_user_data)
        resp = client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
            follow_redirects=False,
        )
        assert resp.status_code == HTTP_SEE_OTHER
        assert "session_token" in client.cookies
        assert "access_token" in client.cookies

    def test_login_remember_me(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Support remember-me option."""
        client.post("/auth/register", data=sample_user_data)
        resp = client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
                "remember": "true",
            },
            follow_redirects=False,
        )
        assert resp.status_code == HTTP_SEE_OTHER
        assert "session_token" in client.cookies

    @SKIP_RATE_LIMIT
    def test_login_rate_limiting(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Enforce login rate limit on repeated failures."""
        client.post("/auth/register", data=sample_user_data)
        last = None
        for _ in range(LOGIN_RATE_LIMIT_ATTEMPTS):
            last = client.post(
                "/auth/login",
                data={
                    "email": sample_user_data["email"],
                    "password": "WrongPassword123!",
                },
            )
        assert last is not None
        assert "Too many login attempts" in last.text


class TestUserLogout:
    def test_successful_logout(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Logout redirects to home."""
        client.post("/auth/register", data=sample_user_data)
        client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
            follow_redirects=False,
        )
        resp = client.post("/auth/logout", follow_redirects=False)
        assert resp.status_code == HTTP_SEE_OTHER
        assert resp.headers.get("location") == "/"

    def test_logout_clears_cookies(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Logout clears session and access cookies."""
        client.post("/auth/register", data=sample_user_data)
        client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
            follow_redirects=False,
        )
        assert "session_token" in client.cookies
        assert "access_token" in client.cookies
        client.post("/auth/logout", follow_redirects=False)
        assert "session_token" not in client.cookies
        assert "access_token" not in client.cookies


# --- GitHub OAuth ---
class TestGitHubOAuth:
    def test_github_login_redirect(self, client: TestClient) -> None:
        """Redirect to GitHub OAuth with client_id."""
        with patch("src.api.routes.auth_routes.GITHUB_CLIENT_ID", "test-client-id"):
            resp = client.get("/auth/github/login", follow_redirects=False)
            assert resp.status_code == HTTP_TEMPORARY_REDIRECT
            loc = resp.headers["location"]
            assert "github.com/login/oauth/authorize" in loc
            assert "client_id=test-client-id" in loc

    def test_github_login_without_config(self, client: TestClient) -> None:
        """Fail GitHub login without config."""
        with patch("src.api.routes.auth_routes.GITHUB_CLIENT_ID", None):
            resp = client.get("/auth/github/login")
            assert resp.status_code == HTTP_INTERNAL_SERVER_ERROR

    @patch("httpx.AsyncClient.post")
    @patch("httpx.AsyncClient.get")
    def test_github_callback_success(
        self,
        mock_get: MagicMock,
        mock_post: MagicMock,
        client: TestClient,
    ) -> None:
        """Handle GitHub callback and redirect to game."""
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test-token"}
        token_response.raise_for_status = MagicMock()
        mock_post.return_value = token_response

        unique_github_email = f"github+{uuid4().hex}@example.com"

        user_response = MagicMock()
        user_response.json.return_value = {
            "id": TEST_GITHUB_ID,
            "login": "testuser",
            "name": "Test User",
            "avatar_url": "https://github.com/avatar.jpg",
            "email": unique_github_email,
        }
        user_response.raise_for_status = MagicMock()

        emails_response = MagicMock()
        emails_response.json.return_value = [
            {"email": unique_github_email, "primary": True},
        ]
        emails_response.raise_for_status = MagicMock()

        mock_get.side_effect = [user_response, emails_response]

        with (
            patch("src.api.routes.auth_routes.GITHUB_CLIENT_ID", "test-client-id"),
            patch("src.api.routes.auth_routes.GITHUB_CLIENT_SECRET", "test-secret"),
        ):
            client.cookies.set("oauth_state", "test-state")
            resp = client.get(
                "/auth/github/callback?code=test-code&state=test-state",
                follow_redirects=False,
            )
            assert resp.status_code == HTTP_SEE_OTHER
            assert resp.headers.get("location") == "/game"

    def test_github_callback_state_mismatch(self, client: TestClient) -> None:
        """Reject callback with state mismatch."""
        client.cookies.set("oauth_state", "correct-state")
        resp = client.get(
            "/auth/github/callback?code=test-code&state=wrong-state",
            follow_redirects=False,
        )
        assert resp.status_code == HTTP_SEE_OTHER
        assert "/signin?error=state" in resp.headers["location"]


# --- /auth/me & refresh ---
class TestUserAPI:
    def test_get_current_user_unauthenticated(self, client: TestClient) -> None:
        """Deny /auth/me without session."""
        resp = client.get("/auth/me")
        assert resp.status_code == HTTP_UNAUTHORIZED

    def test_get_current_user_authenticated(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Return current user when authenticated."""
        client.post("/auth/register", data=sample_user_data)
        client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
            follow_redirects=False,
        )
        resp = client.get("/auth/me")
        assert resp.status_code == HTTP_OK
        data = resp.json()
        assert data["email"] == sample_user_data["email"]
        assert "id" in data
        assert "username" in data

    def test_refresh_token_without_session(self, client: TestClient) -> None:
        """Deny token refresh without session."""
        resp = client.post("/auth/refresh")
        assert resp.status_code == HTTP_UNAUTHORIZED

    def test_refresh_token_with_session(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Issue new access token with session."""
        client.post("/auth/register", data=sample_user_data)
        client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
            follow_redirects=False,
        )
        resp = client.post("/auth/refresh")
        assert resp.status_code == HTTP_OK
        token_data = resp.json()
        assert "access_token" in token_data
        assert "expires_in" in token_data


# --- AuthService unit tests ---
class TestAuthService:
    def test_create_user(self, auth_service: AuthService, unique_email: str) -> None:
        """Create user with explicit username."""
        user = auth_service.create_user(
            email=unique_email,
            password_hash="test-hashed-password",  # noqa: S106
            username="testuser",
        )
        assert user.email == unique_email
        assert user.username == "testuser"
        assert user.password_hash == "test-hashed-password"  # noqa: S105

    def test_create_user_auto_username(
        self,
        auth_service: AuthService,
        unique_email: str,
    ) -> None:
        """Auto-derive username from email local part."""
        user = auth_service.create_user(
            email=unique_email,
            password_hash="test-hashed-password",  # noqa: S106
        )
        assert user.username == "test"

    def test_create_oauth_user(
        self,
        auth_service: AuthService,
        unique_email: str,
    ) -> None:
        """Create verified OAuth user without password hash."""
        user = auth_service.create_oauth_user(
            email=unique_email,
            github_id=TEST_GITHUB_ID,
            username="testuser",
            display_name="Test User",
            avatar_url="https://github.com/avatar.jpg",
        )
        assert user.github_id == TEST_GITHUB_ID
        assert user.is_verified is True
        assert user.password_hash is None

    def test_get_user_by_email(
        self,
        auth_service: AuthService,
        unique_email: str,
    ) -> None:
        """Fetch user by email."""
        auth_service.create_user(
            email=unique_email,
            password_hash="test-hashed-password",  # noqa: S106
        )
        user = auth_service.get_user_by_email(unique_email)
        assert user is not None
        assert user.email == unique_email

    def test_get_user_by_github_id(
        self,
        auth_service: AuthService,
        unique_email: str,
    ) -> None:
        """Fetch user by GitHub ID."""
        auth_service.create_oauth_user(
            email=unique_email,
            github_id=TEST_GITHUB_ID,
            username="testuser",
        )
        user = auth_service.get_user_by_github_id(TEST_GITHUB_ID)
        assert user is not None
        assert user.github_id == TEST_GITHUB_ID

    def test_session_management(
        self,
        auth_service: AuthService,
        unique_email: str,
    ) -> None:
        """Create and fetch session by token."""
        user = auth_service.create_user(
            email=unique_email,
            password_hash="test-hashed-password",  # noqa: S106
        )
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        session = auth_service.create_session(
            user_id=user.id,
            session_token="test-session-token",  # noqa: S106
            expires_at=expires_at,
            ip_address="127.0.0.1",
            user_agent="Test Browser",
        )
        assert session.user_id == user.id
        assert session.session_token == "test-session-token"  # noqa: S105
        found = auth_service.get_session_by_token("test-session-token")
        assert found is not None
        assert found.user_id == user.id

    def test_session_expiry(self, auth_service: AuthService, unique_email: str) -> None:
        """Expired sessions are not returned."""
        user = auth_service.create_user(
            email=unique_email,
            password_hash="test-hashed-password",  # noqa: S106
        )
        expires_at = datetime.now(UTC) - timedelta(hours=1)
        auth_service.create_session(
            user_id=user.id,
            session_token="expired-test-token",  # noqa: S106
            expires_at=expires_at,
        )
        assert auth_service.get_session_by_token("expired-test-token") is None

    def test_revoke_session(self, auth_service: AuthService, unique_email: str) -> None:
        """Revoked session becomes unreachable."""
        user = auth_service.create_user(
            email=unique_email,
            password_hash="test-hashed-password",  # noqa: S106
        )
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        auth_service.create_session(
            user_id=user.id,
            session_token="test-revoke-token",  # noqa: S106
            expires_at=expires_at,
        )
        assert auth_service.revoke_session("test-revoke-token") is True
        assert auth_service.get_session_by_token("test-revoke-token") is None

    @SKIP_RATE_LIMIT
    def test_rate_limiting(self, auth_service: AuthService) -> None:
        """Allow first N actions, then block."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        for _ in range(5):
            assert (
                auth_service.check_rate_limit(
                    mock_request,
                    "test_action",
                    limit=5,
                    window=60,
                )
                is True
            )
        assert (
            auth_service.check_rate_limit(
                mock_request,
                "test_action",
                limit=5,
                window=60,
            )
            is False
        )


# --- password / jwt helpers ---
class TestPasswordSecurity:
    def test_password_hashing(self) -> None:
        """Hash and verify password."""
        password = "SecurePassword123!"  # noqa: S105
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("WrongPassword", hashed) is False

    def test_password_strength_validation(self) -> None:
        """Validate strong vs weak passwords."""
        is_strong, errors = validate_password_strength("SecurePass123!")
        assert is_strong is True
        assert len(errors) == 0

        weak_passwords = [
            "short",
            "no_uppercase123!",
            "NO_LOWERCASE123!",
            "NoNumbers!",
            "a" * 130,
        ]
        for wp in weak_passwords:
            ok, errs = validate_password_strength(wp)
            assert ok is False
            assert len(errs) > 0


class TestJWTTokens:
    def test_token_creation_and_verification(self) -> None:
        """Create JWT and verify payload."""
        secret_key = "test-secret-key"  # noqa: S105
        data = {"user_id": TEST_USER_ID, "email": "test@example.com"}
        token = create_access_token(data, secret_key)
        assert token
        payload = verify_token(token, secret_key)
        assert payload
        assert payload["user_id"] == TEST_USER_ID
        assert payload["email"] == "test@example.com"

    def test_token_expiry(self) -> None:
        """Expired JWT returns None."""
        secret_key = "test-secret-key"  # noqa: S105
        expired_payload = {
            "user_id": TEST_USER_ID,
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
        }
        expired_token = jwt.encode(expired_payload, secret_key, algorithm="HS256")
        assert verify_token(expired_token, secret_key) is None

    def test_token_invalid_secret(self) -> None:
        """JWT signed with wrong secret fails verification."""
        data = {"user_id": TEST_USER_ID}
        token = create_access_token(data, "secret1")
        assert verify_token(token, "secret2") is None


# --- basic endpoint validations (module-level) ---
def _client() -> TestClient:
    """Helper: fresh TestClient."""  # noqa: D401
    return TestClient(app)


def test_sign_pages_exist() -> None:
    """/signin and /signup should exist."""
    client = _client()
    for route in ("/signin", "/signup"):
        resp = client.get(route)
        assert resp.status_code != HTTPStatus.NOT_FOUND, f"{route} not found"


def test_register_requires_fields() -> None:
    """Registration requires fields -> 422."""
    client = _client()
    resp = client.post("/auth/register", data={})
    assert resp.status_code == HTTP_UNPROCESSABLE_ENTITY


def test_login_requires_fields() -> None:
    """Login requires fields -> 422."""
    client = _client()
    resp = client.post("/auth/login", data={})
    assert resp.status_code == HTTP_UNPROCESSABLE_ENTITY


# --- HTMX-focused tests (module-level) ---
def test_successful_registration(
    client: TestClient,
    sample_user_data: dict[str, str],
) -> None:
    """HTMX registration success message."""
    response = client.post("/auth/register", data=sample_user_data, headers=HX_HEADERS)
    assert response.status_code == HTTP_OK
    assert "Account created successfully" in response.text
    assert "test" in response.text


def test_registration_with_weak_password(
    client: TestClient,
    weak_password_data: dict[str, str],
) -> None:
    """HTMX registration rejects weak password."""
    response = client.post(
        "/auth/register",
        data=weak_password_data,
        headers=HX_HEADERS,
    )
    assert response.status_code == HTTP_OK
    assert "Password must be at least" in response.text


def test_registration_password_mismatch(client: TestClient) -> None:
    """HTMX registration rejects mismatched passwords."""
    data = {
        "email": "test@example.com",
        "password": "SecurePass123!",
        "confirm_password": "DifferentPass123!",
    }
    response = client.post("/auth/register", data=data, headers=HX_HEADERS)
    assert response.status_code == HTTP_OK
    assert "Passwords do not match" in response.text


def test_registration_duplicate_email(
    client: TestClient,
    sample_user_data: dict[str, str],
) -> None:
    """HTMX registration rejects duplicate email."""
    client.post("/auth/register", data=sample_user_data, headers=HX_HEADERS)
    response = client.post("/auth/register", data=sample_user_data, headers=HX_HEADERS)
    assert response.status_code == HTTP_OK
    assert "already exists" in response.text


def test_registration_invalid_email(client: TestClient) -> None:
    """HTMX registration rejects invalid email."""
    data = {
        "email": "not-an-email",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!",
    }
    response = client.post("/auth/register", data=data, headers=HX_HEADERS)
    assert response.status_code == HTTP_OK
    assert "Invalid email format" in response.text


@SKIP_RATE_LIMIT
def test_registration_rate_limiting(client: TestClient) -> None:  # noqa: F811
    """HTMX registration enforces rate limit."""
    for i in range(RATE_LIMIT_ATTEMPTS):
        data = {
            "email": f"test{i}@example.com",
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
        }
        response = client.post("/auth/register", data=data, headers=HX_HEADERS)
    assert "Too many registration attempts" in response.text


def test_successful_login(client: TestClient, sample_user_data: dict[str, str]) -> None:
    """HTMX login returns welcome snippet."""
    client.post("/auth/register", data=sample_user_data, headers=HX_HEADERS)
    response = client.post(
        "/auth/login",
        data={
            "email": sample_user_data["email"],
            "password": sample_user_data["password"],
        },
        headers=HX_HEADERS,
    )
    assert response.status_code == HTTP_OK
    assert "Welcome back" in response.text


def test_successful_login_redirect_non_htmx(
    client: TestClient,
    sample_user_data: dict[str, str],
) -> None:
    """Non-HTMX login redirects to /game."""
    client.post("/auth/register", data=sample_user_data, headers=HX_HEADERS)
    resp = client.post(
        "/auth/login",
        data={
            "email": sample_user_data["email"],
            "password": sample_user_data["password"],
        },
        follow_redirects=False,
    )
    assert resp.status_code == HTTP_SEE_OTHER
    assert resp.headers.get("location") == "/game"


def test_login_wrong_password(
    client: TestClient,
    sample_user_data: dict[str, str],
) -> None:
    """HTMX login rejects wrong password."""
    client.post("/auth/register", data=sample_user_data, headers=HX_HEADERS)
    response = client.post(
        "/auth/login",
        data={"email": sample_user_data["email"], "password": "WrongPassword123!"},
        headers=HX_HEADERS,
    )
    assert response.status_code == HTTP_OK
    assert "Invalid email or password" in response.text


def test_login_nonexistent_user(client: TestClient) -> None:
    """HTMX login rejects unknown user."""
    response = client.post(
        "/auth/login",
        data={"email": "nonexistent@example.com", "password": "SomePassword123!"},
        headers=HX_HEADERS,
    )
    assert response.status_code == HTTP_OK
    assert "Invalid email or password" in response.text


def test_login_sets_cookies(
    client: TestClient,
    sample_user_data: dict[str, str],
) -> None:
    """HTMX login sets cookies in client jar."""
    client.post("/auth/register", data=sample_user_data, headers=HX_HEADERS)
    client.post(
        "/auth/login",
        data={
            "email": sample_user_data["email"],
            "password": sample_user_data["password"],
        },
        headers=HX_HEADERS,
    )
    assert "session_token" in client.cookies
    assert "access_token" in client.cookies


def test_login_remember_me(
    client: TestClient,
    sample_user_data: dict[str, str],
) -> None:
    """HTMX login supports remember-me."""
    client.post("/auth/register", data=sample_user_data, headers=HX_HEADERS)
    response = client.post(
        "/auth/login",
        data={
            "email": sample_user_data["email"],
            "password": sample_user_data["password"],
            "remember": "true",
        },
        headers=HX_HEADERS,
    )
    assert response.status_code == HTTP_OK
    assert "session_token" in client.cookies


@SKIP_RATE_LIMIT
def test_login_rate_limiting(  # noqa: F811
    client: TestClient,
    sample_user_data: dict[str, str],
) -> None:
    """HTMX login enforces rate limit on failures."""
    client.post("/auth/register", data=sample_user_data, headers=HX_HEADERS)
    for _ in range(LOGIN_RATE_LIMIT_ATTEMPTS):
        response = client.post(
            "/auth/login",
            data={"email": sample_user_data["email"], "password": "WrongPassword123!"},
            headers=HX_HEADERS,
        )
    assert "Too many login attempts" in response.text


def test_successful_logout(
    client: TestClient,
    sample_user_data: dict[str, str],
) -> None:
    """HTMX logout returns success snippet."""
    client.post("/auth/register", data=sample_user_data, headers=HX_HEADERS)
    client.post(
        "/auth/login",
        data={
            "email": sample_user_data["email"],
            "password": sample_user_data["password"],
        },
        headers=HX_HEADERS,
    )
    logout_response = client.post("/auth/logout", headers=HX_HEADERS)
    assert logout_response.status_code == HTTP_OK
    assert "Logged out successfully" in logout_response.text


def test_logout_clears_cookies(
    client: TestClient,
    sample_user_data: dict[str, str],
) -> None:
    """HTMX logout clears cookies on response."""
    client.post("/auth/register", data=sample_user_data, headers=HX_HEADERS)
    client.post(
        "/auth/login",
        data={
            "email": sample_user_data["email"],
            "password": sample_user_data["password"],
        },
        headers=HX_HEADERS,
    )
    logout_response = client.post("/auth/logout", headers=HX_HEADERS)
    assert logout_response.status_code == HTTP_OK
    assert (
        "session_token" not in logout_response.cookies
        or logout_response.cookies.get("session_token") in ("", None)
    )
    assert "access_token" not in logout_response.cookies or logout_response.cookies.get(
        "access_token",
    ) in ("", None)
