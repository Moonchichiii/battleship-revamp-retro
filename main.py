"""Battleship Revamp ASGI entrypoint (FastAPI + HTMX)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.api.routes.auth_routes import router as auth_router

# Routers
from src.api.routes.game_routes import router as game_router

app = FastAPI(title="Battleship Revamp")

# paths.
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def is_hx(request: Request) -> bool:
    """Return True if the request came from HTMX (HX-Request: true)."""
    return request.headers.get("HX-Request", "").lower() == "true"


@app.get("/health")
async def health() -> dict[str, str]:
    """Check the health status of the application."""
    return {"status": "ok", "ts": datetime.now(UTC).isoformat()}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    """Check the readiness status of the application."""
    return {"status": "ready", "ts": datetime.now(UTC).isoformat()}


@app.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request) -> HTMLResponse:
    """Render the home page."""
    ctx = {"request": request, "active_tab": "home"}
    tpl = "home.html"
    return templates.TemplateResponse(request, tpl, ctx)


@app.get("/game", response_class=HTMLResponse, name="game")
async def game_page(request: Request) -> HTMLResponse:
    """Render the game page."""
    ctx = {"request": request, "active_tab": "game"}
    tpl = "game.html"
    return templates.TemplateResponse(request, tpl, ctx)


@app.get("/scores", response_class=HTMLResponse, name="scores")
async def scores_page(request: Request) -> HTMLResponse:
    """Render the scores page."""
    ctx = {"request": request, "active_tab": "scores"}
    tpl = "scores.html"
    return templates.TemplateResponse(request, tpl, ctx)


@app.get("/signin", response_class=HTMLResponse, name="signin")
async def signin_page(request: Request) -> HTMLResponse:
    """Render the sign-in page."""
    ctx = {"request": request, "active_tab": "signin"}
    return templates.TemplateResponse(request, "signin.html", ctx)


@app.get("/signup", response_class=HTMLResponse, name="signup")
async def signup_page(request: Request) -> HTMLResponse:
    """Render the sign-up page."""
    ctx = {"request": request, "active_tab": "signup"}
    return templates.TemplateResponse(request, "signup.html", ctx)


# Register routers
app.include_router(game_router)
app.include_router(auth_router)
