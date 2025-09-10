"""Authentication routes (local + GitHub OAuth)."""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any
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

if TYPE_CHECKING:
    from src.api.models.user import (
        AuthenticatedUser,
        AuthService,
        get_auth_service,
        get_current_user,
        optional_authenticated_user,
    )

router = APIRouter(prefix="/auth", tags=["auth"])


ROOT = Path(__file__).resolve().parents[3]
templates = Jinja2Templates(directory=str(ROOT / "templates"))


def _get_secret(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v:
        return v

    p = os.getenv(f"{name}_FILE")
    if p and Path(p).exists():
        # utf-8-sig transparently strips BOM
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


@router.post("/login", response_class=HTMLResponse)
def login(  # noqa: PLR0913
    request: Request,
    response: Response,
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    *,
    remember: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    """Authenticate and start a session."""
    if not auth_service.check_rate_limit(request, "login", 10, 300):
        return templates.TemplateResponse(
            "_auth_result.html",
            {
                "request": request,
                "ok": False,
                "message": "Too many login attempts. Please try again later.",
            },
        )

    email = email.strip().lower()
    user = auth_service.get_user_by_email(email)
    if not user or not user.is_active or not user.password_hash:
        return templates.TemplateResponse(
            "_auth_result.html",
            {
                "request": request,
                "ok": False,
                "message": "Invalid email or password.",
            },
        )

    if not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "_auth_result.html",
            {
                "request": request,
                "ok": False,
                "message": "Invalid email or password.",
            },
        )

    auth_service.update_last_login(user)

    token_data = {"user_id": str(user.id), "email": user.email}
    access_token = create_access_token(token_data, auth_service.secret_key)

    session_expiry = timedelta(days=30) if remember else timedelta(hours=24)
    expires_at = datetime.now(UTC) + session_expiry
    session_token = secrets.token_urlsafe(32)

    auth_service.create_session(
        user_id=user.id,
        session_token=session_token,
        expires_at=expires_at,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    response.set_cookie(
        "session_token",
        session_token,
        max_age=int(session_expiry.total_seconds()),
        httponly=True,
        secure=False,  # set True in prod
        samesite="lax",
    )
    response.set_cookie(
        "access_token",
        access_token,
        max_age=1800,
        httponly=True,
        secure=False,  # set True in prod
        samesite="lax",
    )

    return templates.TemplateResponse(
        "_auth_result.html",
        {
            "request": request,
            "ok": True,
            "message": f"Welcome back, {user.display_name or user.username}!",
            "redirect_url": "/game",
            "user_display": user.display_name or user.username,  # <-- add
        },
    )


@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    confirm_password: Annotated[str, Form(...)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> HTMLResponse:
    """Create a new local account."""
    if not auth_service.check_rate_limit(request, "register", 5, 300):
        return templates.TemplateResponse(
            "_auth_result.html",
            {
                "request": request,
                "ok": False,
                "message": "Too many registration attempts. Please try again later.",
            },
        )

    email = email.strip().lower()
    if not email:
        return templates.TemplateResponse(
            "_auth_result.html",
            {"request": request, "ok": False, "message": "Email is required."},
        )

    if password != confirm_password:
        return templates.TemplateResponse(
            "_auth_result.html",
            {"request": request, "ok": False, "message": "Passwords do not match."},
        )

    is_strong, password_errors = validate_password_strength(password)
    if not is_strong:
        return templates.TemplateResponse(
            "_auth_result.html",
            {"request": request, "ok": False, "message": " ".join(password_errors)},
        )

    if auth_service.get_user_by_email(email):
        return templates.TemplateResponse(
            "_auth_result.html",
            {
                "request": request,
                "ok": False,
                "message": "An account with this email already exists.",
            },
        )

    password_hash = hash_password(password)
    user = auth_service.create_user(email, password_hash)

    return templates.TemplateResponse(
        "_auth_result.html",
        {
            "request": request,
            "ok": True,
            "message": f"Account created successfully for {user.username}!",
            "show_login_link": True,
        },
    )


@router.post("/logout", response_class=HTMLResponse)
async def logout(
    request: Request,
    response: Response,
    current_user: Annotated[
        AuthenticatedUser | None,
        Depends(optional_authenticated_user),
    ],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> HTMLResponse:
    """Revoke session and clear cookies."""
    if current_user:
        token = request.cookies.get("session_token")
        if token:
            auth_service.revoke_session(token)

    response.delete_cookie("session_token", path="/")
    response.delete_cookie("access_token", path="/")

    return templates.TemplateResponse(
        "_auth_result.html",
        {
            "request": request,
            "ok": True,
            "message": "Logged out successfully.",
            "redirect_url": "/",
            "logged_out": True,
        },
    )


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
    )
    return resp


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str,
    state: str,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
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
        resp = RedirectResponse(url="/signin?error=oauth_failed", status_code=303)
        resp.delete_cookie("oauth_state", path="/")
        return resp

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
        secure=False,  # set True in prod
        samesite="lax",
    )
    resp.set_cookie(
        "access_token",
        jwt_token,
        max_age=1800,
        httponly=True,
        secure=False,  # set True in prod
        samesite="lax",
    )
    return resp


@router.get("/me")
async def get_current_user_info(
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user)],
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
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
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
        secure=False,  # set True in prod
        samesite="lax",
    )
    return {"access_token": access_token, "token_type": "bearer", "expires_in": 1800}
