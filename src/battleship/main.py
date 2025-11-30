"""Battleship Revamp ASGI entrypoint (FastAPI + HTMX)."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import RequestResponseEndpoint

from src.battleship.api.routes import scores as scores_routes
from src.battleship.api.routes.ai import router as ai_router
from src.battleship.api.routes.auth import router as auth_router
from src.battleship.api.routes.game import router as game_router

# --- FIXED IMPORTS: Now pointing to src.battleship.* ---
from src.battleship.core.database import TESTING, Base, engine

app = FastAPI(title="Battleship Revamp")

# Performance optimizations
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# --- FIXED PATHS: Pointing to src/battleship/web/ ---
BASE_DIR = Path(__file__).resolve().parent  # This is src/battleship/
STATIC_DIR = BASE_DIR / "web" / "static"  # src/battleship/web/static
TEMPLATES_DIR = BASE_DIR / "web" / "templates"  # src/battleship/web/templates

# Ensure directories exist to prevent startup crashes
if not STATIC_DIR.exists():
    print(f"WARNING: Static dir not found at {STATIC_DIR}")
if not TEMPLATES_DIR.exists():
    print(f"WARNING: Templates dir not found at {TEMPLATES_DIR}")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger(__name__)

# DB Config
DB_AUTO_CREATE = os.getenv("DB_AUTO_CREATE", "0" if TESTING else "1") == "1"


@app.middleware("http")
async def add_cache_headers(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "ts": datetime.now(UTC).isoformat()}


# --- HTML ROUTES ---


@app.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "home.html", {"request": request, "active_tab": "home"}
    )


@app.get("/game", response_class=HTMLResponse, name="game")
async def game_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "game.html", {"request": request, "active_tab": "game"}
    )


@app.get("/scores", response_class=HTMLResponse, name="scores")
async def scores_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "scores.html", {"request": request, "active_tab": "scores"}
    )


@app.get("/signin", response_class=HTMLResponse, name="signin")
async def signin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "signin.html", {"request": request, "active_tab": "signin"}
    )


@app.get("/signup", response_class=HTMLResponse, name="signup")
async def signup_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "signup.html", {"request": request, "active_tab": "signup"}
    )


@app.get("/ai", response_class=HTMLResponse, name="ai_lobby")
async def ai_lobby(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "ai.html", {"request": request, "active_tab": "ai"}
    )


# Register routers
app.include_router(auth_router)
app.include_router(game_router)
app.include_router(ai_router)
app.include_router(scores_routes.router)


@app.on_event("startup")
async def init_db() -> None:
    if not DB_AUTO_CREATE:
        return
    try:
        await run_in_threadpool(Base.metadata.create_all, bind=engine)
        logger.info("Database tables ensured")
    except Exception as e:
        logger.error(f"DB Init Failed: {e}")
