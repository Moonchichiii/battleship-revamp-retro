"""Auth routes for HTMX sign-in/sign-up (partial responses)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.api.core.security import hash_password, verify_password
from src.api.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["auth"])

ROOT = Path(__file__).resolve().parents[3]
templates = Jinja2Templates(directory=str(ROOT / "templates"))

TPL_RESULT = "_auth_result.html"


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    *,
    remember: Annotated[bool, Form()] = False,
    db_session: Annotated[Session, Depends("get_db")],
) -> HTMLResponse:
    """Process sign-in and return an HTMX-friendly partial."""
    _ = remember
    user: User | None = (
        db_session.query(User).filter(User.email == email.strip().lower()).first()
    )
    ok = bool(
        user and user.password_hash and verify_password(password, user.password_hash),
    )
    msg = "Signed in!" if ok else "Invalid credentials."
    return templates.TemplateResponse(
        TPL_RESULT,
        {"request": request, "ok": ok, "message": msg},
    )


@router.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    confirm_password: Annotated[str, Form(...)],
    db_session: Annotated[Session, Depends("get_db")],
) -> HTMLResponse:
    """Create a new user and return an HTMX-friendly partial."""
    if password != confirm_password:
        return templates.TemplateResponse(
            TPL_RESULT,
            {"request": request, "ok": False, "message": "Passwords do not match."},
        )

    email_n = email.strip().lower()
    if db_session.query(User).filter(User.email == email_n).first():
        return templates.TemplateResponse(
            TPL_RESULT,
            {"request": request, "ok": False, "message": "Email already registered."},
        )

    username = email_n.split("@", 1)[0]
    user = User(email=email_n, username=username, password_hash=hash_password(password))
    db_session.add(user)
    db_session.commit()

    masked = f"{username}@…"
    return templates.TemplateResponse(
        TPL_RESULT,
        {
            "request": request,
            "ok": True,
            "message": f"Registration complete for {masked}!",
        },
    )
