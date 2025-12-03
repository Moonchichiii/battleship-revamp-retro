"""Authentication routes: local auth + GitHub/Google OAuth."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from src.battleship.auth.schemas import TokenResponse, UserInfo
from src.battleship.auth.service import AuthServiceLogic
from src.battleship.auth.sso import github_sso, google_sso
from src.battleship.auth.views import AuthRenderer
from src.battleship.users import models as user_models

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Local auth: login / register / logout
# ---------------------------------------------------------------------------


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    auth_service: Annotated[user_models.AuthService, Depends(user_models.get_auth_service)],
    remember_raw: Annotated[str | None, Form(alias="remember")] = None,
) -> Response:
    """Authenticate and start a session."""
    renderer = AuthRenderer(request)
    logic = AuthServiceLogic(auth_service)

    # 1. Rate Limit Check
    if not auth_service.check_rate_limit(request, "login", 10):
        return renderer.render_result("Too many login attempts. Try again later.", success=False)

    # 2. Execute Business Logic
    result = logic.process_login(email, password)

    if not result.success:
        return renderer.render_result(result.error, success=False)

    # 3. Success Handling - Generate Tokens
    user = result.data
    remember = str(remember_raw or "").lower() in {"1", "true", "on", "yes"}

    session_info = logic.generate_session_data(
        user,
        remember,
        request.headers.get("user-agent"),
        request.client.host if request.client else None,
    )

    # 4. Build Response
    is_hx = request.headers.get("HX-Request", "").lower() == "true"
    if is_hx:
        renderer.with_redirect("/game")
        renderer.with_user_display(user.display_name or user.username)
        response = renderer.render_result(f"Welcome back, {user.username}!", success=True)
    else:
        response = RedirectResponse(url="/game", status_code=303)

    # 5. Set Cookies
    cookie_settings = {
        "httponly": True,
        "secure": session_info["secure"],
        "samesite": "lax",
        "path": "/",
    }

    response.set_cookie("session_token", session_info["session_token"], max_age=session_info["max_age"], **cookie_settings)
    response.set_cookie("access_token", session_info["access_token"], max_age=1800, **cookie_settings)

    return response


@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    confirm_password: Annotated[str, Form(...)],
    auth_service: Annotated[user_models.AuthService, Depends(user_models.get_auth_service)],
) -> HTMLResponse:
    """Create a new local account."""
    renderer = AuthRenderer(request)
    logic = AuthServiceLogic(auth_service)

    # 1. Rate Limit Check
    if not auth_service.check_rate_limit(request, "register", 5):
        return renderer.render_result("Too many registration attempts. Try again later.", success=False)

    # 2. Execute Business Logic
    result = logic.process_registration(email, password, confirm_password)

    if not result.success:
        return renderer.render_result(result.error, success=False)

    # 3. Success Response
    user = result.data
    renderer.with_login_link()
    return renderer.render_result(f"Account created successfully for {user.username}!", success=True)


@router.post("/logout", response_class=HTMLResponse)
async def logout(
    request: Request,
    current_user: Annotated[
        user_models.AuthenticatedUser | None,
        Depends(user_models.optional_authenticated_user),
    ],
    auth_service: Annotated[user_models.AuthService, Depends(user_models.get_auth_service)],
) -> Response:
    """Revoke session and clear cookies."""
    if current_user:
        token = request.cookies.get("session_token")
        if token:
            auth_service.revoke_session(token)

    is_hx = request.headers.get("HX-Request", "").lower() == "true"

    if is_hx:
        renderer = AuthRenderer(request)
        renderer.with_redirect("/")
        renderer.with_logout_flag()
        response = renderer.render_result("Logged out successfully.", success=True)
    else:
        response = RedirectResponse(url="/", status_code=303)

    response.delete_cookie("session_token", path="/")
    response.delete_cookie("access_token", path="/")
    return response


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
    auth_service: Annotated[user_models.AuthService, Depends(user_models.get_auth_service)],
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
    auth_service: Annotated[user_models.AuthService, Depends(user_models.get_auth_service)],
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
    sso_user,
    provider: str,
) -> RedirectResponse:
    """Common logic to find/create user and set session cookies."""
    logic = AuthServiceLogic(auth_service)

    # 1. Process SSO user (find or create)
    result = logic.process_sso_user(sso_user, provider)

    if not result.success:
        return RedirectResponse(url="/signin?error=oauth_failed", status_code=303)

    user = result.data

    # 2. Generate Session
    session_info = logic.generate_session_data(
        user,
        remember=True,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    # 3. Build Response
    response = RedirectResponse(url="/game", status_code=303)
    response.delete_cookie("oauth_state")

    cookie_settings = {
        "httponly": True,
        "secure": session_info["secure"],
        "samesite": "lax",
        "path": "/",
    }

    response.set_cookie("session_token", session_info["session_token"], max_age=session_info["max_age"], **cookie_settings)
    response.set_cookie("access_token", session_info["access_token"], max_age=1800, **cookie_settings)

    return response


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
        raise HTTPException(status_code=401, detail="Not authenticated")
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
    auth_service: Annotated[user_models.AuthService, Depends(user_models.get_auth_service)],
) -> TokenResponse:
    """Refresh the access token from a valid session."""
    logic = AuthServiceLogic(auth_service)

    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="No session found")

    result = logic.refresh_access_token(session_token)

    if not result.success:
        raise HTTPException(status_code=401, detail=result.error)

    access_token = result.data

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
