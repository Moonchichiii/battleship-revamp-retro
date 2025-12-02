"""Shared auth helpers used by FastAPI auth routes."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastapi import HTTPException, Request, Response, status
from fastapi.templating import Jinja2Templates
from fastapi_sso.sso.github import GithubSSO
from fastapi_sso.sso.google import GoogleSSO

from src.battleship.core.security import (
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from src.battleship.users import models as user_models

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Templates
# -----------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))

# -----------------------------------------------------------------------------
# Secrets / config helpers
# -----------------------------------------------------------------------------

EMAIL_SYNTAX_ONLY = os.getenv("EMAIL_SYNTAX_ONLY") == "1"


def get_secret(name: str, default: str | None = None) -> str | None:
    """Return a secret from env, *_FILE, or /run/secrets/<name>."""
    v = os.getenv(name)
    if v:
        return v

    p = os.getenv(f"{name}_FILE")
    if p and Path(p).exists():
        return Path(p).read_text(encoding="utf-8-sig").strip()

    guess = Path(f"/run/secrets/{name.lower()}")
    if guess.exists():
        return guess.read_text(encoding="utf-8-sig").strip()

    return default


# --- GITHUB CONFIG ---
GITHUB_CLIENT_ID = get_secret("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = get_secret("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_REDIRECT_URI",
    "http://localhost:8000/auth/github/callback",
)

# --- GOOGLE CONFIG ---
GOOGLE_CLIENT_ID = get_secret("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = get_secret("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/auth/google/callback",
)

# Export for templates
templates.env.globals["GITHUB_CLIENT_ID"] = bool(GITHUB_CLIENT_ID)
templates.env.globals["GOOGLE_CLIENT_ID"] = bool(GOOGLE_CLIENT_ID)


# --- SSO Instances ---
# Warning: allow_insecure_http should only be true in local dev
github_sso = GithubSSO(
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    GITHUB_REDIRECT_URI,
    allow_insecure_http=True,
)

google_sso = GoogleSSO(
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    allow_insecure_http=True,
)


# -----------------------------------------------------------------------------
# Validation helpers (Unchanged)
# -----------------------------------------------------------------------------


def validate_email(email_str: str) -> str:
    """Validate and normalize an email address string."""
    e = email_str.strip().lower()

    # For testing environments, use simpler validation
    if EMAIL_SYNTAX_ONLY or os.getenv("TESTING") == "true":
        import re

        if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", e):
            return e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format",
        )

    # Production validation with email-validator
    try:
        from email_validator import validate_email as _ve

        v = _ve(e, check_deliverability=False)
        return cast("str", v.email)
    except Exception as exc:  # pragma: no cover - library edge cases
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format",
        ) from exc


# -----------------------------------------------------------------------------
# Small helper containers (Unchanged)
# -----------------------------------------------------------------------------


class ResponseContext:
    """Container for template response context."""

    def __init__(self, request: Request, *, ok: bool, message: str) -> None:
        self.context: dict[str, Any] = {
            "request": request,
            "ok": ok,
            "message": message,
        }

    def add_user_display(self, user_display: str) -> ResponseContext:
        self.context["user_display"] = user_display
        return self

    def add_redirect(self, redirect_url: str) -> ResponseContext:
        self.context["redirect_url"] = redirect_url
        return self

    def add_login_link(self) -> ResponseContext:
        self.context["show_login_link"] = True
        return self

    def add_logout_flag(self) -> ResponseContext:
        self.context["logged_out"] = True
        return self

    def build(self) -> Response:
        return templates.TemplateResponse("_auth_result.html", self.context)


class AuthRequest:
    """Container for authentication request data."""

    def __init__(self, request: Request, auth_service: user_models.AuthService) -> None:
        self.request = request
        self.auth_service = auth_service
        self.user: user_models.AuthenticatedUser | None = None
        self.email: str = ""
        self.password: str = ""
        self.remember: bool = False
        self.confirm_password: str = ""

    def set_credentials(self, email: str, password: str) -> AuthRequest:
        self.email = email
        self.password = password
        return self

    def set_remember(self, remember_raw: str | None) -> AuthRequest:
        self.remember = str(remember_raw or "").lower() in {"1", "true", "on", "yes"}
        return self

    def set_confirm_password(self, confirm_password: str) -> AuthRequest:
        self.confirm_password = confirm_password
        return self


# -----------------------------------------------------------------------------
# Local auth helpers (login / register / sessions) (Unchanged)
# -----------------------------------------------------------------------------


def check_rate_limit(
    auth_req: AuthRequest,
    action: str,
    limit: int,
    window: int = 300,
) -> Response | None:
    """Check rate limit and return error response if exceeded."""
    if os.getenv("DISABLE_RATE_LIMIT") == "1":
        return None
    if not auth_req.auth_service.check_rate_limit(
        auth_req.request,
        action,
        limit,
        window,
    ):
        return ResponseContext(
            auth_req.request,
            ok=False,
            message=f"Too many {action} attempts. Please try again later.",
        ).build()
    return None


def validate_login_credentials(auth_req: AuthRequest) -> Response | None:
    """Validate login credentials and return error response if invalid."""
    try:
        validated_email = validate_email(auth_req.email)
    except HTTPException:
        return ResponseContext(
            auth_req.request,
            ok=False,
            message="Invalid email or password.",
        ).build()

    user = auth_req.auth_service.get_user_by_email(validated_email)
    if not user or not user.is_active or not user.password_hash:
        return ResponseContext(
            auth_req.request,
            ok=False,
            message="Invalid email or password.",
        ).build()

    if not verify_password(auth_req.password, user.password_hash):
        return ResponseContext(
            auth_req.request,
            ok=False,
            message="Invalid email or password.",
        ).build()

    auth_req.user = user_models.AuthenticatedUser(
        id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        is_verified=user.is_verified,
        permissions=[],
    )
    return None


def validate_registration_data(auth_req: AuthRequest) -> Response | None:
    """Validate registration data and return error response if invalid."""
    try:
        validated_email = validate_email(auth_req.email)
    except HTTPException:
        return ResponseContext(
            auth_req.request,
            ok=False,
            message="Invalid email format.",
        ).build()

    if auth_req.password != auth_req.confirm_password:
        return ResponseContext(
            auth_req.request,
            ok=False,
            message="Passwords do not match.",
        ).build()

    is_strong, password_errors = validate_password_strength(auth_req.password)
    if not is_strong:
        return ResponseContext(
            auth_req.request,
            ok=False,
            message=" ".join(password_errors),
        ).build()

    if auth_req.auth_service.get_user_by_email(validated_email):
        return ResponseContext(
            auth_req.request,
            ok=False,
            message="An account with this email already exists.",
        ).build()

    password_hash = hash_password(auth_req.password)
    user = auth_req.auth_service.create_user(validated_email, password_hash)
    auth_req.user = user_models.AuthenticatedUser(
        id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        is_verified=user.is_verified,
        permissions=[],
    )
    return None


def create_session_cookies(auth_req: AuthRequest, response: Response) -> None:
    """Create session + access token cookies for a logged-in user."""
    if not getattr(auth_req, "user", None):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error: authenticated user missing.",
        )

    user = auth_req.auth_service.get_user_by_id(auth_req.user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error: user not found.",
        )

    if not getattr(auth_req.auth_service, "secret_key", None):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error: auth service not configured.",
        )

    token_data = {"user_id": str(user.id), "email": user.email}
    access_token = create_access_token(token_data, auth_req.auth_service.secret_key)

    session_expiry = timedelta(days=30) if auth_req.remember else timedelta(hours=24)
    expires_at = datetime.now(UTC) + session_expiry
    session_token = secrets.token_urlsafe(32)

    auth_req.auth_service.create_session(
        user_id=cast("UUID", user.id),
        session_token=session_token,
        expires_at=expires_at,
        ip_address=auth_req.request.client.host if auth_req.request.client else None,
        user_agent=auth_req.request.headers.get("user-agent"),
    )

    response.set_cookie(
        "session_token",
        session_token,
        max_age=int(session_expiry.total_seconds()),
        httponly=True,
        secure=False,  # set True in prod behind HTTPS
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "access_token",
        access_token,
        max_age=1800,
        httponly=True,
        secure=False,  # set True in prod behind HTTPS
        samesite="lax",
        path="/",
    )
