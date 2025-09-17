"""
AI opponents (HTMX fragments), gated to authenticated users.

Tiers (matching README):
- rookie  : 6x6 board (easy)
- veteran : 8x8 board (normal)
- admiral : 10x10 board (hard)

This module returns small HTML fragments directly so no new templates are needed.
"""

from __future__ import annotations

from html import escape
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse

from src.api.models.user import require_authenticated_user
from src.game.game_engine import Game
from src.ai.battleship_ai import create_ai

router = APIRouter(prefix="/ai", tags=["ai"])

# Game session storage: (user_id, tier) -> (Game, BattleshipAI, game_state)
_SESSIONS: dict[tuple[str, str], dict[str, Any]] = {}

# Tiers -> board sizes
TierName = Literal["rookie", "veteran", "admiral"]
_TIERS: dict[str, int] = {"rookie": 6, "veteran": 8, "admiral": 10}


def _key(user_id: str, tier: str) -> tuple[str, str]:
    """Build the dictionary key for a user+tier."""
    return (user_id, tier)


def _render_stats(player_game: Game, ai_game: Game, turn: str) -> str:
    """Return a small stats bar for the current game state."""
    player_stats = player_game.get_stats()
    ai_stats = ai_game.get_stats()

    return (
        "<div class='stats' style='margin:.75rem 0;display:flex;gap:1rem;flex-wrap:wrap'>"
        f"<span>Your shots: {player_stats['shots_fired']}</span>"
        f"<span>Your hits: {player_stats['hits']}</span>"
        f"<span>Your accuracy: {player_stats['accuracy']}%</span>"
        f"<span>Ships remaining: {player_stats['ships_remaining']}/{player_stats['total_ship_cells']}</span>"
        f"<span>AI hits on you: {ai_stats['hits']}</span>"
        f"<span>Turn: {turn.title()}</span>"
        f"<span>Board: {player_stats['board_size']}x{player_stats['board_size']}</span>"
        "</div>"
    )


def _render_board(tier: str, player_game: Game, ai_game: Game, turn: str) -> str:
    """Render the clickable grid for player shots."""
    rows: list[str] = []
    rows.append("<div style='overflow:auto'>")
    rows.append("<h4>Enemy Waters (Your Target)</h4>")
    rows.append("<table class='grid' role='grid' aria-label='Battleship board'>")

    for y in range(player_game.size):
        rows.append("<tr role='row'>")
        for x in range(player_game.size):
            cell = player_game.cells[y][x]
            label = "•"
            classes: list[str] = ["cell"]
            aria: list[str] = []
            disabled = turn != "player"

            if cell["hit"]:
                label = "✳"
                classes.append("hit")
                aria.append("hit")
                disabled = True
            elif cell["miss"]:
                label = "×"  # noqa: RUF001
                classes.append("miss")
                aria.append("miss")
                disabled = True
            else:
                aria.append("unknown")

            disabled_attr = "disabled" if disabled else ""
            rows.append(
                "<td role='gridcell'>"
                f"<button "
                f"class='btn cell-btn {' '.join(classes)}' "
                f"aria-label='Fire at {x},{y} ({' '.join(aria)})' "
                f"hx-post='/ai/shot' "
                f'hx-vals=\'{{"x": {x}, "y": {y}, "tier": "{escape(tier)}"}}\' '
                f"hx-target='#main' hx-swap='innerHTML' "
                f"{disabled_attr}>"
                f"{label}"
                "</button>"
                "</td>",
            )
        rows.append("</tr>")
    rows.append("</table>")

    # Add AI's view of your board
    rows.append("<h4 style='margin-top:1rem'>Your Fleet (AI's Target)</h4>")
    rows.append("<table class='grid' role='grid' aria-label='Your ships'>")

    for y in range(ai_game.size):
        rows.append("<tr role='row'>")
        for x in range(ai_game.size):
            cell = ai_game.cells[y][x]
            label = "•"
            classes = ["cell", "readonly"]

            if cell["hit"]:
                label = "💥"  # Your ship was hit
                classes.append("enemy-hit")
            elif cell["miss"]:
                label = "○"  # AI missed
                classes.append("enemy-miss")

            rows.append(
                "<td role='gridcell'>"
                f"<div class='btn {' '.join(classes)}'>{label}</div>"
                "</td>",
            )
        rows.append("</tr>")
    rows.append("</table>")
    rows.append("</div>")

    return "".join(rows)


def _render_lobby(user: Any) -> str:  # noqa: ANN401
    """Render the tier selection lobby."""
    return (
        "<section id='ai-lobby' class='panel is-active'>"
        "<h2>AI Opponents</h2>"
        "<p>Select a difficulty level:</p>"
        "<div class='btn-row' style='display:flex;gap:.5rem;flex-wrap:wrap'>"
        + "".join(
            f"<button class='btn' hx-post='/ai/start' "
            f'hx-vals=\'{{"tier":"{t}"}}\' '
            f"hx-target='#main' hx-swap='innerHTML'>"
            f"{t.title()} ({size}x{size})</button>"
            for t, size in _TIERS.items()
        )
        + "</div>"
        "<div style='margin-top:1rem;font-size:0.9rem;color:var(--g-text-soft)'>"
        "<p><strong>Rookie:</strong> Random moves with basic hit follow-up</p>"
        "<p><strong>Veteran:</strong> Uses checkerboard pattern and hunt mode</p>"
        "<p><strong>Admiral:</strong> Advanced probability-based targeting</p>"
        "</div>"
        "<p style='margin-top:.75rem;color:var(--g-text-soft)'>"
        f"Signed in as <strong>{escape(user.username)}</strong>."
        "</p>"
        "</section>"
    )


def _render_game_screen(tier: str, session_data: dict[str, Any]) -> str:
    """Render the full game panel (back button + stats + board)."""
    player_game = session_data["player_game"]
    ai_game = session_data["ai_game"]
    turn = session_data["turn"]
    last_ai_move = session_data.get("last_ai_move")

    title = f"AI: {tier.title()}"

    # Check for game over
    player_won = player_game.ships.issubset(player_game.hits)
    ai_won = ai_game.ships.issubset(ai_game.hits)

    game_over_msg = ""
    if player_won:
        game_over_msg = (
            "<div class='notice success'>🎉 Victory! You sunk all enemy ships!</div>"
        )
    elif ai_won:
        game_over_msg = (
            "<div class='notice error'>💀 Defeat! The AI sunk your fleet!</div>"
        )

    ai_move_info = ""
    if last_ai_move:
        ai_move_info = (
            f"<div class='ai-move' style='margin:.5rem 0;padding:.5rem;background:var(--g-soft);border-radius:var(--radius)'>"
            f"<strong>AI's last move:</strong> ({last_ai_move.x}, {last_ai_move.y}) - {last_ai_move.reasoning}"
            f"</div>"
        )

    return (
        "<section id='ai-game' class='panel is-active'>"
        f"<h2>{escape(title)}</h2>"
        "<div style='margin-bottom:.5rem'>"
        "<button class='btn btn-secondary' "
        "hx-get='/ai' hx-target='#main' hx-swap='innerHTML' aria-label='Back to AI lobby'>← Back</button>"
        "</div>"
        f"{game_over_msg}"
        f"{_render_stats(player_game, ai_game, turn)}"
        f"{ai_move_info}"
        f"{_render_board(tier, player_game, ai_game, turn)}"
        "</section>"
    )


@router.get("/", response_class=HTMLResponse)
def ai_lobby(
    user: Annotated[Any, Depends(require_authenticated_user)],  # noqa: ANN401
) -> HTMLResponse:
    """AI lobby (requires login)."""
    return HTMLResponse(_render_lobby(user))


@router.post("/start", response_class=HTMLResponse)
def start_game(
    tier: Annotated[str, Form()],
    user: Annotated[Any, Depends(require_authenticated_user)],  # noqa: ANN401
) -> HTMLResponse:
    """Create or reset a game for the given tier and return the board."""
    tier_norm = tier.strip().lower()
    if tier_norm not in _TIERS:
        raise HTTPException(status_code=404, detail="Unknown tier")

    board_size = _TIERS[tier_norm]

    # Create two games: one for player shots, one for AI shots
    player_game = Game.new(size=board_size)  # Player shooting at AI ships
    ai_game = Game.new(size=board_size)  # AI shooting at player ships

    # Create AI opponent
    ai_opponent = create_ai(tier_norm, player_game)

    session_data = {
        "player_game": player_game,
        "ai_game": ai_game,
        "ai_opponent": ai_opponent,
        "turn": "player",  # Player goes first
        "last_ai_move": None,
    }

    _SESSIONS[_key(user.id, tier_norm)] = session_data
    return HTMLResponse(_render_game_screen(tier_norm, session_data))


@router.post("/shot", response_class=HTMLResponse)
def player_shot(
    x: Annotated[int, Form()],
    y: Annotated[int, Form()],
    tier: Annotated[str, Form()],
    user: Annotated[Any, Depends(require_authenticated_user)],  # noqa: ANN401
) -> HTMLResponse:
    """Apply a player shot, then let AI respond."""
    tier_norm = tier.strip().lower()
    session_data = _SESSIONS.get(_key(user.id, tier_norm))
    if not session_data:
        raise HTTPException(status_code=404, detail="No active game")

    player_game = session_data["player_game"]
    ai_game = session_data["ai_game"]
    ai_opponent = session_data["ai_opponent"]

    # Check if it's player's turn
    if session_data["turn"] != "player":
        return HTMLResponse(_render_game_screen(tier_norm, session_data))

    # Apply player's shot
    player_result = player_game.fire(x, y)

    # Check if player won
    if player_result.get("won"):
        session_data["turn"] = "game_over"
        return HTMLResponse(_render_game_screen(tier_norm, session_data))

    # Skip AI turn if it was a repeat shot
    if not player_result.get("repeat"):
        # Now AI's turn
        session_data["turn"] = "ai"

        # AI makes its move
        ai_move = ai_opponent.make_move()
        ai_result = ai_game.fire(ai_move.x, ai_move.y)

        # Update AI's knowledge with keyword-only argument
        ai_opponent.update_game_state(
            ai_move.x,
            ai_move.y,
            hit=ai_result.get("hit", False),
        )

        session_data["last_ai_move"] = ai_move

        # Check if AI won
        if ai_result.get("won"):
            session_data["turn"] = "game_over"
        else:
            session_data["turn"] = "player"

    return HTMLResponse(_render_game_screen(tier_norm, session_data))
