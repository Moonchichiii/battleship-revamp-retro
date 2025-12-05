"""OAuth configuration and provider instances."""

from __future__ import annotations

from pathlib import Path

from decouple import config
from fastapi.templating import Jinja2Templates
from fastapi_sso.sso.github import GithubSSO
from fastapi_sso.sso.google import GoogleSSO

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))

# --- CONFIGURATION ---
GITHUB_CLIENT_ID = config("GITHUB_CLIENT_ID", default=None)
GITHUB_CLIENT_SECRET = config("GITHUB_CLIENT_SECRET", default=None)
GITHUB_REDIRECT_URI = config(
    "GITHUB_REDIRECT_URI", default="http://localhost:8000/auth/github/callback"
)

GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID", default=None)
GOOGLE_CLIENT_SECRET = config("GOOGLE_CLIENT_SECRET", default=None)
GOOGLE_REDIRECT_URI = config(
    "GOOGLE_REDIRECT_URI", default="http://localhost:8000/auth/google/callback"
)

# Export flags to Jinja2
templates.env.globals["GITHUB_CLIENT_ID"] = bool(GITHUB_CLIENT_ID)
templates.env.globals["GOOGLE_CLIENT_ID"] = bool(GOOGLE_CLIENT_ID)

# --- INSTANCES ---
github_sso = GithubSSO(
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    GITHUB_REDIRECT_URI,
    allow_insecure_http=True,
)

google_sso = GoogleSSO(
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    allow_insecure_http=True,
)
