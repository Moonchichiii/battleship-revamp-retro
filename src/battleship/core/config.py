from __future__ import annotations

from typing import Final

from decouple import config


def _optional_str(name: str) -> str | None:
    """Return env var as stripped string, or None if unset/blank."""
    value = config(name, default="", cast=str).strip()
    return value or None


ENVIRONMENT: Final[str] = config("ENVIRONMENT", default="production")
DEBUG: Final[bool] = ENVIRONMENT != "production"

SECRET_KEY: Final[str] = config("SECRET_KEY", default="super-secret-dev-key")

APP_VERSION: Final[str] = config("APP_VERSION", default="dev")

# --- OAuth: GitHub ---
GITHUB_CLIENT_ID: Final[str | None] = _optional_str("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET: Final[str | None] = _optional_str("GITHUB_CLIENT_SECRET")

# --- OAuth: Google ---
GOOGLE_CLIENT_ID: Final[str | None] = _optional_str("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET: Final[str | None] = _optional_str("GOOGLE_CLIENT_SECRET")

# --- OAuth Enabled Flags ---
GITHUB_OAUTH_ENABLED: Final[bool] = bool(
    GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET
)
GOOGLE_OAUTH_ENABLED: Final[bool] = bool(
    GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET
)
