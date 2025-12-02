"""Authentication routes: local auth + GitHub/Google OAuth."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi_sso.sso.base import OpenID

from src.battleship.auth.schemas import TokenResponse, UserInfo
from src.battleship.auth.service import (
    AuthRequest,
    ResponseContext,
    check_rate_limit,
    create_session_cookies,
    github_sso,
    google_sso,
    validate_login_credentials,
    validate_registration_data,
)
from src.battleship.core.security import create_access_token
from src.battleship.users import models as user_models

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Local auth: login / register / logout
# ---------------------------------------------------------------------------


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

        if error_response := check_rate_limit(auth_req, "login", 10):
            return error_response

        if error_response := validate_login_credentials(auth_req):
            return error_response

        user = auth_service.get_user_by_email(auth_req.email)
        if not user:
            raise HTTPException(status_code=400, detail="Invalid login state")

        auth_service.update_last_login(user)

        is_hx = request.headers.get("HX-Request", "").lower() == "true"

        if is_hx:
            resp_inner: Response = (
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

        create_session_cookies(auth_req, resp_inner)
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

        if error_response := check_rate_limit(auth_req, "register", 5):
            return cast(HTMLResponse, error_response)

        if error_response := validate_registration_data(auth_req):
            return cast(HTMLResponse, error_response)

        user = auth_service.get_user_by_email(auth_req.email)
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
    except Exception:
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


# ---------------------------------------------------------------------------
# OAuth Logic (Unified)
# ---------------------------------------------------------------------------


@router.get("/github/login")
async def github_login():
    """Redirect to GitHub."""
    return await github_sso.get_login_redirect()


@router.get("/google/login")
async def google_login():
    """Redirect to Google."""
    return await google_sso.get_login_redirect()


@router.get("/github/callback")
async def github_callback(
    request: Request,
    auth_service: Annotated[
        user_models.AuthService, Depends(user_models.get_auth_service)
    ],
):
    """Handle GitHub return."""
    try:
        user_info = await github_sso.verify_and_process(request)
        return await process_sso_login(request, auth_service, user_info, "github")
    except Exception as e:
        logger.error(f"GitHub Auth Error: {e}")
        return RedirectResponse(url="/signin?error=oauth_failed", status_code=303)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    auth_service: Annotated[
        user_models.AuthService, Depends(user_models.get_auth_service)
    ],
):
    """Handle Google return."""
    try:
        user_info = await google_sso.verify_and_process(request)
        return await process_sso_login(request, auth_service, user_info, "google")
    except Exception as e:
        logger.error(f"Google Auth Error: {e}")
        return RedirectResponse(url="/signin?error=oauth_failed", status_code=303)


async def process_sso_login(
    request: Request,
    auth_service: user_models.AuthService,
    sso_user: OpenID,
    provider: str,
) -> RedirectResponse:
    """Common logic to find/create user and set session cookies."""

    # 1. Try to find user by Provider ID
    user = None
    if provider == "github":
        user = auth_service.get_user_by_github_id(sso_user.id)
    elif provider == "google":
        user = auth_service.get_user_by_google_id(sso_user.id)

    # 2. If not found by ID, try Email (Account Linking)
    if not user and sso_user.email:
        user = auth_service.get_user_by_email(sso_user.email)
        if user:
            # Link the account
            if provider == "github":
                auth_service.update_user_oauth_info(user, github_id=sso_user.id)
            elif provider == "google":
                auth_service.update_user_oauth_info(user, google_id=sso_user.id)

    # 3. If still no user, Create New
    if not user:
        base_name = sso_user.display_name or (
            sso_user.email.split("@")[0] if sso_user.email else "user"
        )

        user = auth_service.create_oauth_user(
            email=sso_user.email,
            username=base_name,
            github_id=sso_user.id if provider == "github" else None,
            google_id=sso_user.id if provider == "google" else None,
            display_name=sso_user.display_name,
            avatar_url=sso_user.picture,
        )

    # 4. Create Session
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

    # 5. Return Redirect
    resp = RedirectResponse(url="/game", status_code=303)
    resp.delete_cookie("oauth_state")

    resp.set_cookie(
        "session_token",
        session_token,
        max_age=int(session_expiry.total_seconds()),
        httponly=True,
        secure=False,  # Set based on env in prod
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


# ---------------------------------------------------------------------------
# Small JSON endpoints
# ---------------------------------------------------------------------------


@router.get("/me", response_model=UserInfo, response_model_exclude_none=True)
async def get_current_user_info(
    current_user: Annotated[
        user_models.AuthenticatedUser | None,
        Depends(user_models.get_current_user),
    ],
) -> UserInfo:
    """Return the current user."""
    if not current_user:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )
    return UserInfo(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        is_verified=current_user.is_verified,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    auth_service: Annotated[
        user_models.AuthService,
        Depends(user_models.get_auth_service),
    ],
) -> TokenResponse:
    """Refresh the access token from a valid session."""
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="No session found")

    session = auth_service.get_session_by_token(session_token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    user = auth_service.get_user_by_id(str(session.user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    token_data = {"user_id": str(user.id), "email": user.email}
    access_token = create_access_token(token_data, auth_service.secret_key)

    session.last_activity = datetime.now(UTC)
    auth_service.db.commit()

    response.set_cookie(
        "access_token",
        access_token,
        max_age=1800,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )

    return TokenResponse(access_token=access_token)
