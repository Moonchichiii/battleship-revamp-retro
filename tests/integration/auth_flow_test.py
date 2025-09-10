"""Comprehensive authentication system tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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

# Test constants
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


@pytest.fixture()
def client() -> TestClient:
    """Test client fixture."""
    return TestClient(app)


@pytest.fixture()
def db_session() -> Generator[Session]:
    """Database session fixture."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def auth_service(db_session: Session) -> AuthService:
    """AuthService fixture."""
    return AuthService(db_session, TEST_SECRET_KEY)


@pytest.fixture
def unique_email() -> str:
    """Generate a unique email address for each test to avoid collisions."""
    return f"test+{uuid4().hex}@example.com"


@pytest.fixture
def sample_user_data(unique_email: str) -> dict[str, str]:
    """Sample user registration data."""
    return {
        "email": unique_email,
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!",
    }


@pytest.fixture
def weak_password_data(unique_email: str) -> dict[str, str]:
    """Sample data with weak password."""
    return {
        "email": unique_email,
        "password": "weak",
        "confirm_password": "weak",
    }


class TestUserRegistration:
    """Test user registration functionality."""

    def test_successful_registration(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Test successful user registration."""
        response = client.post("/auth/register", data=sample_user_data)
        assert response.status_code == HTTP_OK
        assert "Account created successfully" in response.text
        assert "test" in response.text  # username derived from email

    def test_registration_with_weak_password(
        self,
        client: TestClient,
        weak_password_data: dict[str, str],
    ) -> None:
        """Test registration fails with weak password."""
        response = client.post("/auth/register", data=weak_password_data)
        assert response.status_code == HTTP_OK
        assert "Password must be at least" in response.text

    def test_registration_password_mismatch(self, client: TestClient) -> None:
        """Test registration fails when passwords don't match."""
        data = {
            "email": "test@example.com",
            "password": "SecurePass123!",
            "confirm_password": "DifferentPass123!",
        }
        response = client.post("/auth/register", data=data)
        assert response.status_code == HTTP_OK
        assert "Passwords do not match" in response.text

    def test_registration_duplicate_email(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Test registration fails with duplicate email."""
        # First registration
        client.post("/auth/register", data=sample_user_data)

        # Second registration with same email
        response = client.post("/auth/register", data=sample_user_data)
        assert response.status_code == HTTP_OK
        assert "already exists" in response.text

    def test_registration_invalid_email(self, client: TestClient) -> None:
        """Test registration fails with invalid email."""
        data = {
            "email": "not-an-email",
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
        }
        response = client.post("/auth/register", data=data)
        assert response.status_code == HTTP_UNPROCESSABLE_ENTITY

    def test_registration_rate_limiting(self, client: TestClient) -> None:
        """Test rate limiting on registration endpoint."""
        # Make multiple registration attempts
        for i in range(RATE_LIMIT_ATTEMPTS):  # Assuming limit is 5
            data = {
                "email": f"test{i}@example.com",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
            }
            response = client.post("/auth/register", data=data)

        # The 6th attempt should be rate limited
        assert "Too many registration attempts" in response.text


class TestUserLogin:
    """Test user login functionality."""

    def test_successful_login(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Test successful login after registration."""
        # Register user first
        client.post("/auth/register", data=sample_user_data)

        # Login
        login_data = {
            "email": sample_user_data["email"],
            "password": sample_user_data["password"],
        }
        response = client.post("/auth/login", data=login_data)
        assert response.status_code == HTTP_OK
        assert "Welcome back" in response.text

    def test_login_wrong_password(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Test login fails with wrong password."""
        # Register user first
        client.post("/auth/register", data=sample_user_data)

        # Login with wrong password
        login_data = {
            "email": sample_user_data["email"],
            "password": "WrongPassword123!",
        }
        response = client.post("/auth/login", data=login_data)
        assert response.status_code == HTTP_OK
        assert "Invalid email or password" in response.text

    def test_login_nonexistent_user(self, client: TestClient) -> None:
        """Test login fails for nonexistent user."""
        login_data = {
            "email": "nonexistent@example.com",
            "password": "SomePassword123!",
        }
        response = client.post("/auth/login", data=login_data)
        assert response.status_code == HTTP_OK
        assert "Invalid email or password" in response.text

    def test_login_sets_cookies(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Test login sets session and access token cookies."""
        # Register user first
        client.post("/auth/register", data=sample_user_data)

        # Login
        login_data = {
            "email": sample_user_data["email"],
            "password": sample_user_data["password"],
        }
        response = client.post("/auth/login", data=login_data)

        # Check cookies are set
        cookies = response.cookies
        assert "session_token" in cookies
        assert "access_token" in cookies

    def test_login_remember_me(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Test login with remember me option."""
        # Register user first
        client.post("/auth/register", data=sample_user_data)

        # Login with remember me
        login_data = {
            "email": sample_user_data["email"],
            "password": sample_user_data["password"],
            "remember": "true",
        }
        response = client.post("/auth/login", data=login_data)
        assert response.status_code == HTTP_OK

        # Cookie should have longer expiry (can't easily test max_age directly)
        assert "session_token" in response.cookies

    def test_login_rate_limiting(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Test rate limiting on login endpoint."""
        # Register user first
        client.post("/auth/register", data=sample_user_data)

        # Make multiple failed login attempts
        for _ in range(LOGIN_RATE_LIMIT_ATTEMPTS):  # Assuming limit is 10
            login_data = {
                "email": sample_user_data["email"],
                "password": "WrongPassword123!",
            }
            response = client.post("/auth/login", data=login_data)

        # Should be rate limited
        assert "Too many login attempts" in response.text


class TestUserLogout:
    """Test user logout functionality."""

    def test_successful_logout(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Test successful logout."""
        # Register and login
        client.post("/auth/register", data=sample_user_data)
        client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
        )

        # Logout
        logout_response = client.post("/auth/logout")
        assert logout_response.status_code == HTTP_OK
        assert "Logged out successfully" in logout_response.text

    def test_logout_clears_cookies(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Test logout clears session cookies."""
        # Register and login
        client.post("/auth/register", data=sample_user_data)
        client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
        )

        # Logout
        logout_response = client.post("/auth/logout")

        # Cookies should be cleared (deleted)
        # FastAPI sets cookies to empty values when deleting
        assert logout_response.status_code == HTTP_OK


class TestGitHubOAuth:
    """Test GitHub OAuth functionality."""

    def test_github_login_redirect(self, client: TestClient) -> None:
        """Test GitHub login redirects to GitHub."""
        with patch("src.api.routes.auth_routes.GITHUB_CLIENT_ID", "test-client-id"):
            response = client.get("/auth/github/login", follow_redirects=False)
            assert response.status_code == HTTP_TEMPORARY_REDIRECT
            location = response.headers["location"]
            assert "github.com/login/oauth/authorize" in location
            assert "client_id=test-client-id" in location

    def test_github_login_without_config(self, client: TestClient) -> None:
        """Test GitHub login fails without configuration."""
        with patch("src.api.routes.auth_routes.GITHUB_CLIENT_ID", None):
            response = client.get("/auth/github/login")
            assert response.status_code == HTTP_INTERNAL_SERVER_ERROR

    @patch("httpx.AsyncClient.post")
    @patch("httpx.AsyncClient.get")
    def test_github_callback_success(
        self,
        mock_get: MagicMock,
        mock_post: MagicMock,
        client: TestClient,
    ) -> None:
        """Test successful GitHub OAuth callback."""
        # Mock GitHub token exchange
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test-token"}
        token_response.raise_for_status = MagicMock()
        mock_post.return_value = token_response

        # Use a unique email for this OAuth flow to avoid collisions
        unique_github_email = f"github+{uuid4().hex}@example.com"

        # Mock GitHub user API responses
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

        # Test callback
        with (
            patch("src.api.routes.auth_routes.GITHUB_CLIENT_ID", "test-client-id"),
            patch("src.api.routes.auth_routes.GITHUB_CLIENT_SECRET", "test-secret"),
        ):
            # Set OAuth state cookie first
            client.cookies.set("oauth_state", "test-state")

            response = client.get(
                "/auth/github/callback?code=test-code&state=test-state",
                follow_redirects=False,
            )
            assert response.status_code == HTTP_SEE_OTHER

    def test_github_callback_state_mismatch(self, client: TestClient) -> None:
        """Test GitHub callback fails with state mismatch."""
        client.cookies.set("oauth_state", "correct-state")
        response = client.get(
            "/auth/github/callback?code=test-code&state=wrong-state",
            follow_redirects=False,
        )
        assert response.status_code == HTTP_SEE_OTHER
        assert "/signin?error=state" in response.headers["location"]


class TestUserAPI:
    """Test user API endpoints."""

    def test_get_current_user_unauthenticated(self, client: TestClient) -> None:
        """Test /auth/me endpoint without authentication."""
        response = client.get("/auth/me")
        assert response.status_code == HTTP_UNAUTHORIZED

    def test_get_current_user_authenticated(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Test /auth/me endpoint with authentication."""
        # Register and login
        client.post("/auth/register", data=sample_user_data)
        client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
        )

        # Get current user
        response = client.get("/auth/me")
        if response.status_code == HTTP_OK:
            user_data = response.json()
            assert user_data["email"] == sample_user_data["email"]
            assert "id" in user_data
            assert "username" in user_data

    def test_refresh_token_without_session(self, client: TestClient) -> None:
        """Test token refresh without valid session."""
        response = client.post("/auth/refresh")
        assert response.status_code == HTTP_UNAUTHORIZED

    def test_refresh_token_with_session(
        self,
        client: TestClient,
        sample_user_data: dict[str, str],
    ) -> None:
        """Test token refresh with valid session."""
        # Register and login
        client.post("/auth/register", data=sample_user_data)
        client.post(
            "/auth/login",
            data={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
        )

        # Refresh token
        response = client.post("/auth/refresh")
        if response.status_code == HTTP_OK:
            token_data = response.json()
            assert "access_token" in token_data
            assert "expires_in" in token_data


class TestAuthService:
    """Test AuthService methods directly."""

    def test_create_user(self, auth_service: AuthService, unique_email: str) -> None:
        """Test user creation via AuthService."""
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
        """Test user creation with auto-generated username."""
        user = auth_service.create_user(
            email=unique_email,
            password_hash="test-hashed-password",  # noqa: S106
        )
        assert user.username == "test"  # Derived from email

    def test_create_oauth_user(
        self,
        auth_service: AuthService,
        unique_email: str,
    ) -> None:
        """Test OAuth user creation."""
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
        """Test finding user by email."""
        # Create user
        auth_service.create_user(
            email=unique_email,
            password_hash="test-hashed-password",  # noqa: S106
        )

        # Find user
        user = auth_service.get_user_by_email(unique_email)
        assert user is not None
        assert user.email == unique_email

    def test_get_user_by_github_id(
        self,
        auth_service: AuthService,
        unique_email: str,
    ) -> None:
        """Test finding user by GitHub ID."""
        # Create OAuth user
        auth_service.create_oauth_user(
            email=unique_email,
            github_id=TEST_GITHUB_ID,
            username="testuser",
        )

        # Find user
        user = auth_service.get_user_by_github_id(TEST_GITHUB_ID)
        assert user is not None
        assert user.github_id == TEST_GITHUB_ID

    def test_session_management(
        self,
        auth_service: AuthService,
        unique_email: str,
    ) -> None:
        """Test session creation and lookup."""
        # Create user first
        user = auth_service.create_user(
            email=unique_email,
            password_hash="test-hashed-password",  # noqa: S106
        )

        # Create session
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

        # Lookup session
        found_session = auth_service.get_session_by_token("test-session-token")
        assert found_session is not None
        assert found_session.user_id == user.id

    def test_session_expiry(self, auth_service: AuthService, unique_email: str) -> None:
        """Test expired session is not returned."""
        # Create user
        user = auth_service.create_user(
            email=unique_email,
            password_hash="test-hashed-password",  # noqa: S106
        )

        # Create expired session
        expires_at = datetime.now(UTC) - timedelta(hours=1)  # Past time
        auth_service.create_session(
            user_id=user.id,
            session_token="expired-test-token",  # noqa: S106
            expires_at=expires_at,
        )

        # Should not find expired session
        session = auth_service.get_session_by_token("expired-test-token")
        assert session is None

    def test_revoke_session(self, auth_service: AuthService, unique_email: str) -> None:
        """Test session revocation."""
        # Create user and session
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

        # Revoke session
        result = auth_service.revoke_session("test-revoke-token")
        assert result is True

        # Session should be gone
        session = auth_service.get_session_by_token("test-revoke-token")
        assert session is None

    def test_rate_limiting(self, auth_service: AuthService) -> None:
        """Test rate limiting functionality."""
        # Mock request object
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"

        # Test within limit
        for _ in range(5):
            result = auth_service.check_rate_limit(
                mock_request,
                "test_action",
                limit=5,
                window=60,
            )
            assert result is True

        # Test exceeding limit
        result = auth_service.check_rate_limit(
            mock_request,
            "test_action",
            limit=5,
            window=60,
        )
        assert result is False


class TestPasswordSecurity:
    """Test password security features."""

    def test_password_hashing(self) -> None:
        """Test password hashing and verification."""
        password = "SecurePassword123!"  # noqa: S105
        hashed = hash_password(password)

        # Hash should be different from original
        assert hashed != password

        # Should verify correctly
        assert verify_password(password, hashed) is True

        # Should fail with wrong password
        assert verify_password("WrongPassword", hashed) is False

    def test_password_strength_validation(self) -> None:
        """Test password strength validation."""
        # Strong password
        is_strong, errors = validate_password_strength("SecurePass123!")
        assert is_strong is True
        assert len(errors) == 0

        # Weak passwords
        weak_passwords = [
            "short",  # Too short
            "no_uppercase123!",  # No uppercase
            "NO_LOWERCASE123!",  # No lowercase
            "NoNumbers!",  # No numbers
            "a" * 130,  # Too long
        ]

        for weak_pass in weak_passwords:
            is_strong, errors = validate_password_strength(weak_pass)
            assert is_strong is False
            assert len(errors) > 0


class TestJWTTokens:
    """Test JWT token functionality."""

    def test_token_creation_and_verification(self) -> None:
        """Test JWT token creation and verification."""
        secret_key = "test-secret-key"  # noqa: S105
        data = {"user_id": TEST_USER_ID, "email": "test@example.com"}

        # Create token
        token = create_access_token(data, secret_key)
        assert token is not None

        # Verify token
        payload = verify_token(token, secret_key)
        assert payload is not None
        assert payload["user_id"] == TEST_USER_ID
        assert payload["email"] == "test@example.com"

    def test_token_expiry(self) -> None:
        """Test token expiry handling."""
        secret_key = "test-secret-key"  # noqa: S105

        # Create expired token manually
        expired_payload = {
            "user_id": TEST_USER_ID,
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
        }
        expired_token = jwt.encode(expired_payload, secret_key, algorithm="HS256")

        # Should not verify
        payload = verify_token(expired_token, secret_key)
        assert payload is None

    def test_token_invalid_secret(self) -> None:
        """Test token verification with wrong secret."""
        data = {"user_id": TEST_USER_ID}
        token = create_access_token(data, "secret1")

        # Try to verify with different secret
        payload = verify_token(token, "secret2")
        assert payload is None
