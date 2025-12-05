"""Battleship Revamp ASGI entrypoint (FastAPI + HTMX)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from decouple import config as env_config
from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.sessions import SessionMiddleware

from src.battleship.api.routes import scores as scores_routes
from src.battleship.api.routes.ai import router as ai_router
from src.battleship.api.routes.auth import router as auth_router
from src.battleship.api.routes.game import router as game_router
from src.battleship.core.config import (
    APP_VERSION,
    ENVIRONMENT,
    GITHUB_OAUTH_ENABLED,
    GOOGLE_OAUTH_ENABLED,
    SECRET_KEY,
)
from src.battleship.core.database import TESTING, Base, engine

logger = logging.getLogger(__name__)

DB_AUTO_CREATE = (
    env_config("DB_AUTO_CREATE", default="0" if TESTING else "1", cast=str) == "1"
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if DB_AUTO_CREATE:
        try:
            await run_in_threadpool(Base.metadata.create_all, bind=engine)
            logger.info("Database tables ensured")
        except Exception as e:
            logger.error("DB Init Failed: %s", e)
    yield


app = FastAPI(title="Battleship Revamp", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "web" / "static"
TEMPLATES_DIR = BASE_DIR / "web" / "templates"

if not STATIC_DIR.exists():
    print(f"WARNING: Static dir not found at {STATIC_DIR}")
if not TEMPLATES_DIR.exists():
    print(f"WARNING: Templates dir not found at {TEMPLATES_DIR}")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

templates.env.globals["STATIC_VERSION"] = APP_VERSION
templates.env.globals["ENVIRONMENT"] = ENVIRONMENT
templates.env.globals["GITHUB_OAUTH_ENABLED"] = GITHUB_OAUTH_ENABLED
templates.env.globals["GOOGLE_OAUTH_ENABLED"] = GOOGLE_OAUTH_ENABLED


@app.middleware("http")
async def add_cache_headers(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=600"
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "ts": datetime.now(UTC).isoformat()}


@app.head("/")
async def home_head() -> Response:
    return Response(status_code=200)


@app.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "home.html", {"active_tab": "home"})


@app.get("/game", response_class=HTMLResponse, name="game")
async def game_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "game.html", {"active_tab": "game"})


@app.get("/scores", response_class=HTMLResponse, name="scores")
async def scores_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "scores.html", {"active_tab": "scores"})


@app.get("/signin", response_class=HTMLResponse, name="signin")
async def signin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "signin.html", {"active_tab": "signin"})


@app.get("/signup", response_class=HTMLResponse, name="signup")
async def signup_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "signup.html", {"active_tab": "signup"})


@app.get("/ai", response_class=HTMLResponse, name="ai_lobby")
async def ai_lobby(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "ai.html", {"active_tab": "ai"})


app.include_router(auth_router)
app.include_router(game_router)
app.include_router(ai_router)
app.include_router(scores_routes.router)
