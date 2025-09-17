"""HTMX routes for Battleship gameplay with user authentication and scoring."""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.game.game_engine import Game


from src.api.models.user import (
    AuthenticatedUser,
    AuthService,
    get_auth_service,
    optional_authenticated_user,
)


logger = logging.getLogger(__name__)

router = APIRouter()

ROOT = Path(__file__).resolve().parents[3]
templates = Jinja2Templates(directory=str(ROOT / "templates"))


class AITier(Enum):
    """AI difficulty tiers."""

    ROOKIE = "rookie"
    VETERAN = "veteran"
    ADMIRAL = "admiral"


# Simple game storage (will move to database later)
_user_games: dict[str, Game] = {}
_guest_game: Game | None = None


def get_user_game(
    user: AuthenticatedUser | None,
    size: int = 8,
    ai_tier: str = "rookie",
) -> Game:
    """Get or create a game for the current user/guest."""
    if user:
        # Authenticated user - use persistent per-user game
        user_id = user.id
        game_key = f"{user_id}_{size}_{ai_tier}"
        if game_key not in _user_games:
            _user_games[game_key] = Game.new(size)
        return _user_games[game_key]

    # Guest user - single shared game by size
    if _guest_game is None or _guest_game.size != size:
        # Using module-level variable for guest games (simple approach)
        globals()["_guest_game"] = Game.new(size)

    # At this point _guest_game is guaranteed to exist and be the right size
    return _guest_game  # type: ignore[return-value]


def reset_user_game(
    user: AuthenticatedUser | None,
    size: int = 8,
    ai_tier: str = "rookie",
) -> Game:
    """Reset the game for the current user/guest."""
    new_game = Game.new(size)

    if user:
        game_key = f"{user.id}_{size}_{ai_tier}"
        _user_games[game_key] = new_game
        return new_game

    # Reset guest game using globals to avoid Ruff global statement warning
    globals()["_guest_game"] = new_game
    return new_game


async def save_user_score(
    user: AuthenticatedUser,
    game: Game,
    auth_service: AuthService,
) -> None:
    """Save the user's score when they complete a game."""
    try:
        from src.api.routes.scores_routes import ScoreService, save_game_score

        stats = game.get_stats()

        # Only save if game is completed
        if not stats["game_over"]:
            return

        # Save the score using the scores service
        score_service = ScoreService(auth_service)
        score_record = save_game_score(
            user_id=uuid.UUID(user.id),
            game_stats=stats,
            score_service=score_service,
        )
        logger.info(
            "Score saved! User %s scored %d points!",
            user.username,
            score_record.score,
        )
    except (ValueError, TypeError, ImportError):
        logger.exception("Failed to save score for %s", user.username)


@router.post("/new", response_class=HTMLResponse)
async def new_game(
    request: Request,
    current_user: Annotated[
        AuthenticatedUser | None,
        Depends(optional_authenticated_user),
    ],
    board_size: Annotated[int, Form()] = 8,
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
    """Create a new game with the specified board size and AI tier."""
    size = max(6, min(10, board_size))

    # Validate AI tier
    try:
        ai_level = AITier(ai_tier)
    except ValueError:
        ai_level = AITier.ROOKIE

    game = reset_user_game(current_user, size, ai_level.value)

    return templates.TemplateResponse(
        request,
        "_board.html",
        {
            "board": game,
            "current_user": current_user,
            "ai_tier": ai_level.value,
            "is_guest": current_user is None,
        },
    )


@router.post("/reset", response_class=HTMLResponse)
async def reset_game(
    request: Request,
    current_user: Annotated[
        AuthenticatedUser | None,
        Depends(optional_authenticated_user),
    ],
    board_size: Annotated[int, Form()] = 8,
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
    """Reset the game with the specified board size and AI tier."""
    size = max(6, min(10, board_size))

    # Validate AI tier
    try:
        ai_level = AITier(ai_tier)
    except ValueError:
        ai_level = AITier.ROOKIE

    game = reset_user_game(current_user, size, ai_level.value)

    return templates.TemplateResponse(
        request,
        "_board.html",
        {
            "board": game,
            "current_user": current_user,
            "ai_tier": ai_level.value,
            "is_guest": current_user is None,
        },
    )


@router.post("/shot/{x:int}/{y:int}", response_class=HTMLResponse)
async def shot(  # noqa: PLR0913
    x: int,
    y: int,
    request: Request,
    current_user: Annotated[
        AuthenticatedUser | None,
        Depends(optional_authenticated_user),
    ],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    board_size: Annotated[int, Form()] = 8,
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
    """Handle a shot fired at the specified coordinates."""
    size = max(6, min(10, board_size))

    # Validate AI tier
    try:
        ai_level = AITier(ai_tier)
    except ValueError:
        ai_level = AITier.ROOKIE

    game = get_user_game(current_user, size, ai_level.value)

    if 0 <= x < game.size and 0 <= y < game.size:
        result = game.fire(x, y)

        # If game is won and user is authenticated, save their score
        if result.get("won") and current_user:
            await save_user_score(current_user, game, auth_service)

    return templates.TemplateResponse(
        request,
        "_board.html",
        {
            "board": game,
            "current_user": current_user,
            "ai_tier": ai_level.value,
            "is_guest": current_user is None,
        },
    )


@router.get("/game-status", response_class=HTMLResponse)
async def game_status(
    request: Request,
    current_user: Annotated[
        AuthenticatedUser | None,
        Depends(optional_authenticated_user),
    ],
    ai_tier: str = "rookie",
) -> HTMLResponse:
    """Retrieve the current game status."""
    # Validate AI tier
    try:
        ai_level = AITier(ai_tier)
    except ValueError:
        ai_level = AITier.ROOKIE

    game = get_user_game(current_user, ai_tier=ai_level.value)
    stats = game.get_stats()

    return templates.TemplateResponse(
        request,
        "_game_status.html",
        {
            "status": stats,
            "current_user": current_user,
            "ai_tier": ai_level.value,
            "is_guest": current_user is None,
        },
    )
