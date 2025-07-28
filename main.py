"""
Battleship Revamp - FastAPI + HTMX.

Modern Battleship game built with FastAPI for performance and HTMX for interactivity.
"""

from datetime import UTC, datetime

from fastapi import FastAPI

app = FastAPI(title="Battleship Revamp")


@app.get("/")
async def home() -> dict[str, str]:
    """Return a welcome message."""
    return {"message": "Welcome to Battleship Revamp!"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return service health status."""
    return {
        "status": "healthy",
        "service": "battleship-revamp",
        "timestamp": datetime.now(UTC).isoformat(),
    }
