"""Presentation layer: Handles HTML generation and Response building."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request, Response
from fastapi.templating import Jinja2Templates

# Setup Templates
BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))

class AuthRenderer:
    """Builder pattern for HTMX HTML responses."""

    def __init__(self, request: Request) -> None:
        self.request = request
        self._context: dict[str, Any] = {}

    def with_redirect(self, url: str) -> AuthRenderer:
        self._context["redirect_url"] = url
        return self

    def with_user_display(self, name: str) -> AuthRenderer:
        self._context["user_display"] = name
        return self

    def with_login_link(self) -> AuthRenderer:
        self._context["show_login_link"] = True
        return self

    def with_logout_flag(self) -> AuthRenderer:
        self._context["logged_out"] = True
        return self

    def render_result(self, message: str, success: bool = False, **kwargs: Any) -> Response:
        """Render the standard auth result fragment."""
        self._context.update({
            "ok": success,
            "message": message,
            **kwargs
        })
        return templates.TemplateResponse(self.request, "_auth_result.html", self._context)
