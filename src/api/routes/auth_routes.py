"""Auth routes for demo sign-in and sign-up (HTMX partial responses)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/auth", tags=["auth"])

ROOT = Path(__file__).resolve().parents[3]
templates = Jinja2Templates(directory=str(ROOT / "templates"))


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    *,
    remember: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    """HTMX sign-in handler (demo only)."""
    _ = remember

    ok = bool(email and password)
    msg = "Signed in!" if ok else "Invalid credentials."

    return templates.TemplateResponse(
        "_auth_result.html",
        {
            "request": request,
            "ok": ok,
            "message": msg,
        },
    )


@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    confirm_password: Annotated[str, Form(...)],
) -> HTMLResponse:
    """HTMX registration handler (demo only)."""
    if password != confirm_password:
        return templates.TemplateResponse(
            "_auth_result.html",
            {
                "request": request,
                "ok": False,
                "message": "Passwords do not match.",
            },
        )

    local = email.split("@", 1)[0] if "@" in email else email
    masked = f"{local}@…"

    return templates.TemplateResponse(
        "_auth_result.html",
        {
            "request": request,
            "ok": True,
            "message": f"Registration complete for {masked}!",
        },
    )
