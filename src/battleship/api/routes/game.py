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

# Points to src/battleship/web/templates
BASE_DIR = Path(__file__).resolve().parents[2]  # src/battleship
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Single standard board size for this HTMX game
STANDARD_BOARD_SIZE = DEFAULT_BOARD_SIZE  # currently 8x8


# AI difficulty tiers (user-facing names)
class AITier(Enum):
    """AI difficulty tiers."""

    ROOKIE = "rookie"
    VETERAN = "veteran"
    ADMIRAL = "admiral"


# Map difficulty tier -> internal AiOpponent difficulty label
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


# In-memory session store: key -> SessionState
# key = "<user_id_or_guest>|<ai_tier>"
_SESSIONS: dict[str, SessionState] = {}


def _session_key(user: AuthenticatedUser | None, ai_tier: str) -> str:
    """Build a simple session key based on user (or guest) and AI tier."""
    user_part = user.id if user else "guest"
    return f"{user_part}|{ai_tier}"


def _new_session() -> SessionState:
    """Create a brand-new session with the standard board size."""
    return SessionState(
        player_target=Game.new(size=STANDARD_BOARD_SIZE),
        ai_target=Game.new(size=STANDARD_BOARD_SIZE),
    )


def get_user_session(
    user: AuthenticatedUser | None,
    ai_tier: str,
) -> SessionState:
    """Get or create a session for a user/tier."""
    key = _session_key(user, ai_tier)
    if key not in _SESSIONS:
        _SESSIONS[key] = _new_session()
    return _SESSIONS[key]


def reset_user_session(
    user: AuthenticatedUser | None,
    ai_tier: str,
) -> SessionState:
    """Reset a user/tier session to a fresh game."""
    key = _session_key(user, ai_tier)
    session = _new_session()
    _SESSIONS[key] = session
    return session


# ---------------------------------------------------------------------------
# Score saving helper
# ---------------------------------------------------------------------------


async def save_user_score(
    user: AuthenticatedUser,
    game: Game,
    auth_service: AuthService,
) -> None:
    """Persist a finished game's score for an authenticated user."""
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
            "Score saved: user=%s score=%d shots=%d accuracy=%.1f board=%d",
            user.username,
            score_record.score,
            score_record.shots_fired,
            score_record.accuracy,
            score_record.board_size,
        )
    except Exception:  # noqa: BLE001
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
    """Handle one player move + AI response, return updated board fragment."""
    session = get_user_session(current_user, ai_level.value)
    player_board = session.player_target
    ai_board = session.ai_target

    # If game is already over, just re-render current state
    if session.player_won or session.ai_won:
        context = {
            "board": player_board,
            "current_user": current_user,
            "ai_tier": ai_level.value,
            "is_guest": current_user is None,
            "status_message": "Game over. Start a new mission to play again.",
            "status_log": session.log,
            "game_stats": player_board.get_stats(),
        }
        return templates.TemplateResponse(request, "_board.html", context)

    # Basic bounds check
    if not (0 <= x < player_board.size and 0 <= y < player_board.size):
        context = {
            "board": player_board,
            "current_user": current_user,
            "ai_tier": ai_level.value,
            "is_guest": current_user is None,
            "status_message": "Invalid move. Stay within the grid.",
            "status_log": session.log,
            "game_stats": player_board.get_stats(),
        }
        return templates.TemplateResponse(request, "_board.html", context)

    messages: list[str] = []

    # ------------------------------------------------------------------
    # Player fires
    # ------------------------------------------------------------------
    result = player_board.fire(x, y)

    if result.get("repeat"):
        status_message = f"Already targeted ({x + 1}, {y + 1})."
        session.append_log(status_message)
        context = {
            "board": player_board,
            "current_user": current_user,
            "ai_tier": ai_level.value,
            "is_guest": current_user is None,
            "status_message": status_message,
            "status_log": session.log,
            "game_stats": player_board.get_stats(),
        }
        return templates.TemplateResponse(request, "_board.html", context)

    if result.get("hit"):
        messages.append(f"HIT at ({x + 1}, {y + 1})!")
        if result.get("won"):
            messages.append("VICTORY! Enemy fleet eliminated.")
            if current_user:
                await save_user_score(current_user, player_board, auth_service)
    else:
        messages.append(f"MISS at ({x + 1}, {y + 1}).")

    # ------------------------------------------------------------------
    # AI fires back (only if player hasn't already won)
    # ------------------------------------------------------------------
    if not result.get("won"):
        difficulty_label = AI_DIFFICULTY_MAP.get(ai_level, "novice")
        ai_move_x, ai_move_y = AiOpponent(ai_board).get_best_move(difficulty_label)
        ai_hit_result = ai_board.fire(ai_move_x, ai_move_y)

        if ai_hit_result.get("hit"):
            messages.append(
                f"WARNING: Enemy return fire HIT at ({ai_move_x + 1}, {ai_move_y + 1})!",
            )
        else:
            messages.append(
                f"Enemy return fire missed at ({ai_move_x + 1}, {ai_move_y + 1}).",
            )

    status_message = " ".join(messages)
    session.append_log(status_message)

    # IMPORTANT: recompute stats *after* both moves so UI tracks correctly
    game_stats = player_board.get_stats()

    context = {
        "board": player_board,
        "current_user": current_user,
        "ai_tier": ai_level.value,
        "is_guest": current_user is None,
        "status_message": status_message,
        "status_log": session.log,
        "game_stats": game_stats,
    }
    return templates.TemplateResponse(request, "_board.html", context)


# ---------------------------------------------------------------------------
# HTMX endpoints
# ---------------------------------------------------------------------------


@router.post("/new", response_class=HTMLResponse)
async def new_game(
    request: Request,
    current_user: Annotated[
        AuthenticatedUser | None,
        Depends(optional_authenticated_user),
    ],
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
    """Start a new game with a fixed standard board size."""
    try:
        ai_level = AITier(ai_tier)
    except ValueError:
        ai_level = AITier.ROOKIE

    session = reset_user_session(current_user, ai_level.value)
    session.log.clear()

    context = {
        "board": session.player_target,
        "current_user": current_user,
        "ai_tier": ai_level.value,
        "status_message": "System initialized. Target locked.",
        "status_log": session.log,
        "game_stats": session.player_target.get_stats(),
        "is_guest": current_user is None,
    }
    return templates.TemplateResponse(request, "_board.html", context)


@router.post("/reset", response_class=HTMLResponse)
async def reset_game(
    request: Request,
    current_user: Annotated[
        AuthenticatedUser | None,
        Depends(optional_authenticated_user),
    ],
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
    """Reset the current game (same tier, same standard board size)."""
    return await new_game(request, current_user, ai_tier)


@router.post("/make-move", response_class=HTMLResponse)
async def make_move(
    request: Request,
    current_user: Annotated[
        AuthenticatedUser | None,
        Depends(optional_authenticated_user),
    ],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    x: Annotated[int, Form()],
    y: Annotated[int, Form()],
    ai_tier: Annotated[str, Form()] = "rookie",
) -> HTMLResponse:
    """Handle a single player move + AI response."""
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
