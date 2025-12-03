"""HTMX routes for Battleship gameplay with user authentication and scoring."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.battleship.ai.opponent import AiOpponent
from src.battleship.game.engine import DEFAULT_BOARD_SIZE, Game
from src.battleship.users.models import (
    AuthenticatedUser,
    AuthService,
    get_auth_service,
    optional_authenticated_user,
)

logger = logging.getLogger(__name__)

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STANDARD_BOARD_SIZE = DEFAULT_BOARD_SIZE

class AITier(Enum):
    ROOKIE = "rookie"
    VETERAN = "veteran"
    ADMIRAL = "admiral"

AI_DIFFICULTY_MAP = {
    AITier.ROOKIE: "novice",
    AITier.VETERAN: "intermediate",
    AITier.ADMIRAL: "expert",
}

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    player_target: Game
    ai_target: Game
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

_SESSIONS: dict[str, SessionState] = {}

def _session_key(user: AuthenticatedUser | None, ai_tier: str) -> str:
    user_part = user.id if user else "guest"
    return f"{user_part}|{ai_tier}"

def _new_session() -> SessionState:
    return SessionState(
        player_target=Game.new(size=STANDARD_BOARD_SIZE),
        ai_target=Game.new(size=STANDARD_BOARD_SIZE),
    )

def get_user_session(user: AuthenticatedUser | None, ai_tier: str) -> SessionState:
    key = _session_key(user, ai_tier)
    if key not in _SESSIONS:
        _SESSIONS[key] = _new_session()
    return _SESSIONS[key]

def reset_user_session(user: AuthenticatedUser | None, ai_tier: str) -> SessionState:
    key = _session_key(user, ai_tier)
    session = _new_session()
    _SESSIONS[key] = session
    return session

# ---------------------------------------------------------------------------
# Score saving helper (UPDATED to handle Difficulty)
# ---------------------------------------------------------------------------

async def save_user_score(
    user: AuthenticatedUser,
    game: Game,
    auth_service: AuthService,
    ai_tier: str, # Added ai_tier param
) -> None:
    """Persist a finished game's score."""
    try:
        from src.battleship.api.routes.scores import ScoreService, save_game_score

        stats = game.get_stats()
        if not stats["game_over"]:
            return

        # Inject difficulty into stats so scores.py can read it
        stats["difficulty"] = ai_tier

        score_service = ScoreService(auth_service)
        score_record = save_game_score(
            user_id=uuid.UUID(user.id),
            game_stats=stats,
            score_service=score_service,
        )
        logger.info(
            "Score saved: user=%s score=%d tier=%s",
            user.username,
            score_record.score,
            ai_tier,
        )
    except Exception:
        logger.exception("Failed to save score for %s", user.username)

# ---------------------------------------------------------------------------
# Core turn logic
# ---------------------------------------------------------------------------

async def _take_turn(
    *,
    request: Request,
    current_user: AuthenticatedUser | None,
    auth_service: AuthService,
    x: int,
    y: int,
    ai_level: AITier,
) -> HTMLResponse:
    """Handle one player move + AI response."""
    session = get_user_session(current_user, ai_level.value)
    player_board = session.player_target
    ai_board = session.ai_target

    # Render if game over
    if session.player_won or session.ai_won:
        return _render_board_response(request, session, current_user, ai_level)

    # Basic bounds check
    if not (0 <= x < player_board.size and 0 <= y < player_board.size):
        session.append_log("Invalid coordinates.")
        return _render_board_response(request, session, current_user, ai_level)

    messages: list[str] = []

    # 1. Player fires
    result = player_board.fire(x, y)

    if result.get("repeat"):
        session.append_log(f"Already targeted ({x + 1}, {y + 1}).")
        return _render_board_response(request, session, current_user, ai_level)

    if result.get("hit"):
        messages.append(f"HIT at ({x + 1}, {y + 1})!")
        if result.get("won"):
            messages.append("VICTORY! Enemy fleet eliminated.")
            if current_user:
                # Pass AI Tier here
                await save_user_score(current_user, player_board, auth_service, ai_level.value)
    else:
        messages.append(f"MISS at ({x + 1}, {y + 1}).")

    # 2. AI fires back (if player hasn't won)
    if not result.get("won"):
        difficulty_label = AI_DIFFICULTY_MAP.get(ai_level, "novice")
        ai_move_x, ai_move_y = AiOpponent(ai_board).get_best_move(difficulty_label)
        ai_hit_result = ai_board.fire(ai_move_x, ai_move_y)

        if ai_hit_result.get("hit"):
            messages.append(f"WARNING: Enemy return fire HIT at ({ai_move_x + 1}, {ai_move_y + 1})!")
        else:
            messages.append(f"Enemy return fire missed at ({ai_move_x + 1}, {ai_move_y + 1}).")

    session.append_log(" ".join(messages))
    return _render_board_response(request, session, current_user, ai_level)

def _render_board_response(request, session, current_user, ai_level):
    """Helper to render the board template to avoid code duplication."""
    context = {
        "board": session.player_target,
        "current_user": current_user,
        "ai_tier": ai_level.value,
        "is_guest": current_user is None,
        "status_message": session.log[-1] if session.log else "Ready.",
        "status_log": session.log,
        "game_stats": session.player_target.get_stats(),
    }
    return templates.TemplateResponse("_board.html", context)

# ---------------------------------------------------------------------------
# HTMX endpoints
# ---------------------------------------------------------------------------

@router.post("/new", response_class=HTMLResponse)
async def new_game(
    request: Request,
    current_user: Annotated[AuthenticatedUser | None, Depends(optional_authenticated_user)],
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
    try:
        ai_level = AITier(ai_tier)
    except ValueError:
        ai_level = AITier.ROOKIE

    session = reset_user_session(current_user, ai_level.value)
    session.log.clear()
    session.append_log("System initialized. Target locked.")

    return _render_board_response(request, session, current_user, ai_level)

@router.post("/reset", response_class=HTMLResponse)
async def reset_game(
    request: Request,
    current_user: Annotated[AuthenticatedUser | None, Depends(optional_authenticated_user)],
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
    return await new_game(request, current_user, ai_tier)

@router.post("/make-move", response_class=HTMLResponse)
async def make_move(
    request: Request,
    current_user: Annotated[AuthenticatedUser | None, Depends(optional_authenticated_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    x: Annotated[int, Form()],
    y: Annotated[int, Form()],
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
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
        ai_level=ai_level,
    )
