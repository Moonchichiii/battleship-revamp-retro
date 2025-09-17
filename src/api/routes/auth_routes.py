"""Authentication routes local & GitHub OAuth."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, cast, TYPE_CHECKING
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api.core.security import (
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from src.api.models import user as user_models

if TYPE_CHECKING:
    from uuid import UUID


EMAIL_SYNTAX_ONLY = os.getenv("EMAIL_SYNTAX_ONLY") == "1"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

ROOT = Path(__file__).resolve().parents[3]
templates = Jinja2Templates(directory=str(ROOT / "templates"))


def _get_secret(name: str, default: str | None = None) -> str | None:
    """Return a secret from env, *_FILE, or /run/secrets/<name> (fallback to default)."""
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


# OAuth Configuration
GITHUB_CLIENT_ID = _get_secret("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = _get_secret("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv(
    "OAUTH_REDIRECT_URI",
    "http://localhost:8000/auth/github/callback",
)

templates.env.globals["GITHUB_CLIENT_ID"] = bool(GITHUB_CLIENT_ID)


def validate_email(email_str: str) -> str:
    """Validate and normalize an email address string."""
    e = email_str.strip().lower()

    # For testing environments, use simpler validation
    if EMAIL_SYNTAX_ONLY or os.getenv("TESTING") == "true":
        import re

        # Allow plus signs and other common email patterns for testing
        if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", e):
            return e
        else:  # noqa: RET505
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format",
            )
    else:
        # Production validation with email-validator
        try:
            from email_validator import validate_email as _ve

            v = _ve(e, check_deliverability=False)
            return cast("str", v.email)  # 🔧 ensure the return type is str
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format",
            ) from exc


class ResponseContext:
    """Container for template response context."""

    def __init__(self, request: Request, *, ok: bool, message: str) -> None:
        """Initialize response context."""
        self.context = {
            "request": request,
            "ok": ok,
            "message": message,
        }

    def add_user_display(self, user_display: str) -> ResponseContext:
        """Add user display name to context."""
        self.context["user_display"] = user_display
        return self

    def add_redirect(self, redirect_url: str) -> ResponseContext:
        """Add redirect URL to context."""
        self.context["redirect_url"] = redirect_url
        return self

    def add_login_link(self) -> ResponseContext:
        """Add login link flag to context."""
        self.context["show_login_link"] = True
        return self

    def add_logout_flag(self) -> ResponseContext:
        """Add logout flag to context."""
        self.context["logged_out"] = True
        return self

    def build(self) -> HTMLResponse:
        """Build the template response."""
        return templates.TemplateResponse("_auth_result.html", self.context)


class AuthRequest:
    """Container for authentication request data."""

    def __init__(self, request: Request, auth_service: user_models.AuthService) -> None:
        """Initialize auth request container."""
        self.request = request
        self.auth_service = auth_service
        self.user: user_models.AuthenticatedUser | None = None

    def set_credentials(self, email: str, password: str) -> AuthRequest:
        """Set email and password credentials."""
        self.email = email
        self.password = password
        return self

    def set_remember(self, remember_raw: str | None) -> AuthRequest:
        """Set remember me preference."""
        self.remember = str(remember_raw or "").lower() in {"1", "true", "on", "yes"}
        return self

    def set_confirm_password(self, confirm_password: str) -> AuthRequest:
        """Set password confirmation."""
        self.confirm_password = confirm_password
        return self


def _check_rate_limit(
    auth_req: AuthRequest,
    action: str,
    limit: int,
) -> HTMLResponse | None:
    """Check rate limit and return error response if exceeded."""
    if os.getenv("DISABLE_RATE_LIMIT") == "1":
        return None
    if not auth_req.auth_service.check_rate_limit(auth_req.request, action, limit, 300):
        return ResponseContext(
            auth_req.request,
            ok=False,
            message=f"Too many {action} attempts. Please try again later.",
        ).build()
    return None


def _validate_login_credentials(auth_req: AuthRequest) -> HTMLResponse | None:
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

    auth_req.user = cast("user_models.AuthenticatedUser", user)
    return None


def _validate_registration_data(auth_req: AuthRequest) -> HTMLResponse | None:
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

    # Create user
    password_hash = hash_password(auth_req.password)
    user = auth_req.auth_service.create_user(validated_email, password_hash)
    auth_req.user = cast("user_models.AuthenticatedUser", user)
    return None


def _create_session_cookies(
    auth_req: AuthRequest,
    response: Response,
) -> None:
    """Create session and access token cookies."""
    # Ensure we actually have a user object; previously this relied on an assert.
    if not getattr(auth_req, "user", None):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error: authenticated user missing.",
        )

    user = cast("user_models.AuthenticatedUser", auth_req.user)

    # Ensure the auth service has a secret_key configured.
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
        secure=False,  # True in prod behind HTTPS
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "access_token",
        access_token,
        max_age=1800,
        httponly=True,
        secure=False,  # True in prod behind HTTPS
        samesite="lax",
        path="/",
    )


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    auth_service: Annotated[
        user_models.AuthService,
        Depends(user_models.get_auth_service),
    ],
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    remember_raw: Annotated[str | None, Form(alias="remember")] = None,
) -> Response:
    """Authenticate and start a session."""
    try:
        auth_req = (
            AuthRequest(request, auth_service)
            .set_credentials(email, password)
            .set_remember(remember_raw)
        )

        if error_response := _check_rate_limit(auth_req, "login", 10):
            return error_response

        if error_response := _validate_login_credentials(auth_req):
            return error_response

        user = cast("user_models.AuthenticatedUser", auth_req.user)
        auth_service.update_last_login(cast("user_models.User", user))

        is_hx = request.headers.get("HX-Request", "").lower() == "true"

        resp_inner: Response

        if is_hx:
            resp_inner = (
                ResponseContext(
                    request,
                    ok=True,
                    message=f"Welcome back, {user.display_name or user.username}!",
                )
                .add_user_display(user.display_name or user.username)
                .add_redirect("/game")
                .build()
            )
        else:
            resp_inner = RedirectResponse(url="/game", status_code=303)

        _create_session_cookies(auth_req, resp_inner)
        return resp_inner

    except HTTPException:
        raise
    except Exception:
        logger.exception("Login failed for email %s", email)
        return ResponseContext(
            request,
            ok=False,
            message="Login failed. Please try again.",
        ).build()


@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    confirm_password: Annotated[str, Form(...)],
    auth_service: Annotated[
        user_models.AuthService,
        Depends(user_models.get_auth_service),
    ],
) -> HTMLResponse:
    """Create a new local account."""
    try:
        auth_req = (
            AuthRequest(request, auth_service)
            .set_credentials(email, password)
            .set_confirm_password(confirm_password)
        )

        # Rate limiting
        if error_response := _check_rate_limit(auth_req, "register", 5):
            return error_response

        # Validation
        if error_response := _validate_registration_data(auth_req):
            return error_response

        # Success path
        user = cast("user_models.AuthenticatedUser", auth_req.user)
        return (
            ResponseContext(
                request,
                ok=True,
                message=f"Account created successfully for {user.username}!",
            )
            .add_login_link()
            .build()
        )

    except HTTPException:
        raise
    except (ValueError, TypeError, ConnectionError):
        logger.exception("Registration failed for email %s", email)
        return ResponseContext(
            request,
            ok=False,
            message="Registration failed. Please try again.",
        ).build()


@router.post("/logout", response_class=HTMLResponse)
async def logout(
    request: Request,
    current_user: Annotated[
        user_models.AuthenticatedUser | None,
        Depends(user_models.optional_authenticated_user),
    ],
    auth_service: Annotated[
        user_models.AuthService,
        Depends(user_models.get_auth_service),
    ],
) -> Response:
    """Revoke session and clear cookies."""
    if current_user:
        token = request.cookies.get("session_token")
        if token:
            auth_service.revoke_session(token)

    is_hx = request.headers.get("HX-Request", "").lower() == "true"

    resp_inner: Response = RedirectResponse(url="/", status_code=303)
    if is_hx:
        resp_inner = (
            ResponseContext(request, ok=True, message="Logged out successfully.")
            .add_redirect("/")
            .add_logout_flag()
            .build()
        )

    resp_inner.delete_cookie("session_token", path="/")
    resp_inner.delete_cookie("access_token", path="/")
    return resp_inner


@router.get("/github/login")
async def github_login() -> RedirectResponse:
    """Start GitHub OAuth flow."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub OAuth not configured.",
        )

    state = secrets.token_urlsafe(32)
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "scope": "user:email",
        "state": state,
        "response_type": "code",
    }
    github_auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    resp = RedirectResponse(url=github_auth_url)
    resp.set_cookie(
        "oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=False,  # set True in prod
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str,
    state: str,
    auth_service: Annotated[
        user_models.AuthService,
        Depends(user_models.get_auth_service),
    ],
) -> RedirectResponse:
    """Exchange code, upsert user, start session."""
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or stored_state != state:
        return RedirectResponse(url="/signin?error=state", status_code=303)

    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": GITHUB_REDIRECT_URI,
                },
                headers={"Accept": "application/json"},
            )
            token_resp.raise_for_status()
            access_token = token_resp.json().get("access_token")
            if not access_token:
                return RedirectResponse(url="/signin?error=token", status_code=303)

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
            }

            user_resp = await client.get("https://api.github.com/user", headers=headers)
            user_resp.raise_for_status()
            gh_user = user_resp.json()

            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers=headers,
            )
            emails_resp.raise_for_status()
            emails = emails_resp.json()
            primary_email = next(
                (e["email"] for e in emails if e.get("primary")),
                gh_user.get("email"),
            )
            if not primary_email:
                return RedirectResponse(url="/signin?error=no_email", status_code=303)

    except httpx.HTTPError:
        logger.exception("GitHub OAuth failed")
        resp_err = RedirectResponse(url="/signin?error=oauth_failed", status_code=303)
        resp_err.delete_cookie("oauth_state", path="/")
        return resp_err

    user = auth_service.get_user_by_github_id(gh_user["id"])
    if not user:
        existing = auth_service.get_user_by_email(primary_email)
        if existing:
            user = auth_service.update_user_oauth_info(
                existing,
                github_id=gh_user["id"],
                display_name=gh_user.get("name"),
                avatar_url=gh_user.get("avatar_url"),
            )
        else:
            user = auth_service.create_oauth_user(
                email=primary_email,
                github_id=gh_user["id"],
                username=gh_user["login"],
                display_name=gh_user.get("name"),
                avatar_url=gh_user.get("avatar_url"),
            )

    auth_service.update_last_login(user)

    session_expiry = timedelta(hours=24)
    expires_at = datetime.now(UTC) + session_expiry
    session_token = secrets.token_urlsafe(32)

    auth_service.create_session(
        user_id=user.id,
        session_token=session_token,
        expires_at=expires_at,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    token_data = {"user_id": str(user.id), "email": user.email}
    jwt_token = create_access_token(token_data, auth_service.secret_key)

    resp = RedirectResponse(url="/game", status_code=303)
    resp.delete_cookie("oauth_state", path="/")
    resp.set_cookie(
        "session_token",
        session_token,
        max_age=int(session_expiry.total_seconds()),
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
    resp.set_cookie(
        "access_token",
        jwt_token,
        max_age=1800,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )

    return resp


@router.get("/me")
async def get_current_user_info(
    current_user: Annotated[
        user_models.AuthenticatedUser | None,
        Depends(user_models.get_current_user),
    ],
) -> dict[str, Any]:
    """Return the current user."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "display_name": current_user.display_name,
        "avatar_url": current_user.avatar_url,
        "is_verified": current_user.is_verified,
    }


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    auth_service: Annotated[
        user_models.AuthService,
        Depends(user_models.get_auth_service),
    ],
) -> dict[str, Any]:
    """Refresh the access token from a valid session."""
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session found",
        )

    session = auth_service.get_session_by_token(session_token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    user = auth_service.get_user_by_id(str(session.user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    token_data = {"user_id": str(user.id), "email": user.email}
    access_token = create_access_token(token_data, auth_service.secret_key)

    session.last_activity = datetime.now(UTC)
    auth_service.db.commit()

    response.set_cookie(
        "access_token",
        access_token,
        max_age=1800,
        httponly=True,
        secure=False,  # set True in Prod Behind HTTPS.
        samesite="lax",
        path="/",
    )

    return {"access_token": access_token, "token_type": "bearer", "expires_in": 1800}
