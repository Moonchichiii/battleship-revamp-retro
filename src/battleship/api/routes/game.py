"""HTMX routes for Battleship gameplay with user authentication and scoring."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.battleship.ai.opponent import AiOpponent
from src.battleship.game.engine import Game
from src.battleship.users.models import (
    AuthenticatedUser,
    AuthService,
    get_auth_service,
    optional_authenticated_user,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# --- FIXED PATH LOGIC ---
# Points to src/battleship/web/templates
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # src/battleship
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))


class AITier(Enum):
    """AI difficulty tiers."""

    ROOKIE = "rookie"
    VETERAN = "veteran"
    ADMIRAL = "admiral"


AI_DIFFICULTY_MAP = {
    AITier.ROOKIE: "novice",
    AITier.VETERAN: "intermediate",
    AITier.ADMIRAL: "expert",
}


@dataclass
class SessionState:
    """Keeps both boards for a player vs AI game plus recent log."""

    player_target: Game  # Player shoots at AI fleet
    ai_target: Game  # AI shoots at player fleet
    log: list[str] = field(default_factory=list)

    def append_log(self, message: str) -> None:
        self.log.append(message)
        if len(self.log) > 5:
            self.log.pop(0)

    @property
    def player_won(self) -> bool:
        return self.player_target.ships.issubset(self.player_target.hits)

    @property
    def ai_won(self) -> bool:
        return self.ai_target.ships.issubset(self.ai_target.hits)


# Simple game storage
_user_sessions: dict[str, SessionState] = {}
_guest_session: SessionState | None = None


def _new_session(size: int) -> SessionState:
    return SessionState(
        player_target=Game.new(size),
        ai_target=Game.new(size),
    )


def get_user_session(
    user: AuthenticatedUser | None, size: int = 8, ai_tier: str = "rookie"
) -> SessionState:
    if user:
        user_id = user.id
        game_key = f"{user_id}_{size}_{ai_tier}"
        if game_key not in _user_sessions:
            _user_sessions[game_key] = _new_session(size)
        return _user_sessions[game_key]

    if _guest_session is None or _guest_session.player_target.size != size:
        globals()["_guest_session"] = _new_session(size)
    return cast(SessionState, _guest_session)


def reset_user_session(
    user: AuthenticatedUser | None, size: int = 8, ai_tier: str = "rookie"
) -> SessionState:
    new_session = _new_session(size)
    if user:
        game_key = f"{user.id}_{size}_{ai_tier}"
        _user_sessions[game_key] = new_session
        return new_session
    globals()["_guest_session"] = new_session
    return new_session


async def save_user_score(
    user: AuthenticatedUser, game: Game, auth_service: AuthService
) -> None:
    try:
        from src.battleship.api.routes.scores import ScoreService, save_game_score

        stats = game.get_stats()
        if not stats["game_over"]:
            return
        score_service = ScoreService(auth_service)
        score_record = save_game_score(
            user_id=uuid.UUID(user.id),
            game_stats=stats,
            score_service=score_service,
        )
        logger.info(
            "Score saved! User %s scored %d points!", user.username, score_record.score
        )
    except (ValueError, TypeError, ImportError):
        logger.exception("Failed to save score for %s", user.username)


async def _take_turn(
    *,
    request: Request,
    current_user: AuthenticatedUser | None,
    auth_service: AuthService,
    x: int,
    y: int,
    size: int,
    ai_level: AITier,
) -> HTMLResponse:
    session = get_user_session(current_user, size, ai_level.value)
    player_board = session.player_target
    ai_board = session.ai_target

    context = {
        "board": player_board,
        "current_user": current_user,
        "ai_tier": ai_level.value,
        "is_guest": current_user is None,
        "status_log": session.log,
        "game_stats": player_board.get_stats(),  # Pass stats for OOB updates
    }

    if not (0 <= x < player_board.size and 0 <= y < player_board.size):
        context["status_message"] = "Invalid move. Stay within the grid."
        return templates.TemplateResponse(request, "_board.html", context)

    result = player_board.fire(x, y)
    messages: list[str] = []

    if result.get("repeat"):
        context["status_message"] = f"Already targeted ({x + 1}, {y + 1})."
        return templates.TemplateResponse(request, "_board.html", context)

    if result.get("hit"):
        messages.append(f"HIT at ({x + 1}, {y + 1})!")
        if result.get("won"):
            messages.append("VICTORY! Enemy fleet eliminated.")
            if current_user:
                await save_user_score(current_user, player_board, auth_service)
    else:
        messages.append(f"MISS at ({x + 1}, {y + 1}).")

    if not result.get("won"):
        ai_difficulty = AI_DIFFICULTY_MAP.get(ai_level, "novice")
        ai_move = AiOpponent(ai_board).get_best_move(ai_difficulty)
        ai_hit_result = ai_board.fire(ai_move[0], ai_move[1])

        # Simple AI log logic
        if ai_hit_result.get("hit"):
            messages.append("WARNING: Enemy return fire HIT!")
        else:
            messages.append("Enemy return fire missed.")

    context["status_message"] = " ".join(messages)
    session.append_log(context["status_message"])

    return templates.TemplateResponse(request, "_board.html", context)


@router.post("/new", response_class=HTMLResponse)
async def new_game(
    request: Request,
    current_user: Annotated[
        AuthenticatedUser | None, Depends(optional_authenticated_user)
    ],
    board_size: Annotated[int, Form(alias="board-size")] = 8,
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
    size = max(6, min(10, board_size))
    try:
        ai_level = AITier(ai_tier)
    except ValueError:
        ai_level = AITier.ROOKIE

    session = reset_user_session(current_user, size, ai_level.value)
    session.log.clear()

    return templates.TemplateResponse(
        request,
        "_board.html",
        {
            "board": session.player_target,
            "current_user": current_user,
            "ai_tier": ai_level.value,
            "status_message": "System Initialized. Target locked.",
            "status_log": session.log,
            "game_stats": session.player_target.get_stats(),
        },
    )


@router.post("/reset", response_class=HTMLResponse)
async def reset_game(
    request: Request,
    current_user: Annotated[
        AuthenticatedUser | None, Depends(optional_authenticated_user)
    ],
    board_size: Annotated[int, Form(alias="board-size")] = 8,
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
    return await new_game(request, current_user, board_size, ai_tier)


@router.post("/make-move", response_class=HTMLResponse)
async def make_move(
    request: Request,
    current_user: Annotated[
        AuthenticatedUser | None, Depends(optional_authenticated_user)
    ],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    x: Annotated[int, Form()],
    y: Annotated[int, Form()],
    board_size: Annotated[int, Form(alias="board-size")] = 8,
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
    size = max(6, min(10, board_size))
    try:
        ai_level = AITier(ai_tier)
    except ValueError:
        ai_level = AITier.ROOKIE

    return await _take_turn(
        request=request,
        current_user=current_user,
        auth_service=auth_service,
        x=x,
        y=y,
        size=size,
        ai_level=ai_level,
    )
