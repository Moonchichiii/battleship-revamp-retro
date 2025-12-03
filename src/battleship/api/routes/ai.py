"""
AI opponents (HTMX fragments), gated to authenticated users.
Includes Logic for Standard AI and LLM-based Psy-Ops.
"""

from __future__ import annotations

from html import escape
from typing import Annotated, Any, Literal

from decouple import config
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse

from src.battleship.ai.strategies import create_ai
from src.battleship.game.engine import Game
from src.battleship.users.models import require_authenticated_user

router = APIRouter(prefix="/ai", tags=["ai"])

_SESSIONS: dict[tuple[str, str], dict[str, Any]] = {}

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

    rows.append("<h4 style='margin-top:1rem'>Your Fleet (AI's Target)</h4>")
    rows.append("<table class='grid' role='grid' aria-label='Your ships'>")

    for y in range(ai_game.size):
        rows.append("<tr role='row'>")
        for x in range(ai_game.size):
            cell = ai_game.cells[y][x]
            label = "•"
            classes = ["cell", "readonly"]

            if cell["hit"]:
                label = "💥"
                classes.append("enemy-hit")
            elif cell["miss"]:
                label = "○"
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
    buttons = "".join(
        f"<button class='btn' hx-post='/ai/start' "
        f'hx-vals=\'{{"tier":"{t}"}}\' '
        f"hx-target='#main' hx-swap='innerHTML' hx-push-url='true'>"
        f"{t.title()} ({size}x{size})</button>"
        for t, size in _TIERS.items()
    )

    llm_button = (
        "<button class='btn' "
        "style='border-color: var(--phosphor-alert); color: var(--phosphor-alert);' "
        "hx-post='/ai/start' hx-vals='{\"tier\":\"psy-ops\"}' "
        "hx-target='#main' hx-swap='innerHTML' hx-push-url='true' "
        "hx-indicator='#ai-loader'>"
        "<span style='display: block; font-size: 1.5rem; margin-bottom: 0.5rem;'>☠</span>"
        "PSY-OPS (LLM)"
        "<div class='hint' style='margin-top: 0.5rem'>GPT-4 Powered</div>"
        "</button>"
    )

    return (
        "<section id='ai-lobby' class='panel is-active'>"
        "<h2>AI Opponents</h2>"
        "<p>Select a difficulty level:</p>"
        "<div class='actions' style='justify-content: center; gap: 1rem; flex-wrap: wrap;'>"
        f"{buttons}"
        f"{llm_button}"
        "</div>"
        "<div id='ai-loader' class='htmx-indicator' style='text-align:center; margin-top:1rem;'>"
        "<span class='blink'>ESTABLISHING UPLINK WITH AI CORE...</span>"
        "</div>"
        "<div style='margin-top:1rem;font-size:0.9rem;color:var(--phosphor-dim)'>"
        "<p><strong>Rookie:</strong> Random moves.</p>"
        "<p><strong>Veteran:</strong> Checkerboard & Hunt patterns.</p>"
        "<p><strong>Admiral:</strong> Probability targeting.</p>"
        "<p><strong>Psy-Ops:</strong> LLM reasoning engine (Slow but tactical).</p>"
        "</div>"
        "<p style='margin-top:1.5rem; border-top: 1px dashed var(--phosphor-dim); padding-top: 0.5rem;'>"
        f"LOGGED IN AS: <strong>{escape(user.username)}</strong>"
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
    """Create game. If tier is 'psy-ops', use LLM."""
    tier_norm = tier.strip().lower()

    if tier_norm == "psy-ops":
        board_size = 8
    elif tier_norm in _TIERS:
        board_size = _TIERS[tier_norm]
    else:
        raise HTTPException(status_code=404, detail="Unknown tier")

    player_game = Game.new(size=board_size)
    ai_game = Game.new(size=board_size)

    if tier_norm == "psy-ops":
        api_key = config("OPENAI_API_KEY", default=None)

        if not api_key:
            ai_opponent = create_ai("admiral", player_game)
        else:
            from src.battleship.ai.opponent import LLMAIOpponent

            ai_opponent = LLMAIOpponent(player_game, api_key=api_key)
    else:
        ai_opponent = create_ai(tier_norm, player_game)

    session_data = {
        "player_game": player_game,
        "ai_game": ai_game,
        "ai_opponent": ai_opponent,
        "turn": "player",
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

    if session_data["turn"] != "player":
        return HTMLResponse(_render_game_screen(tier_norm, session_data))

    player_result = player_game.fire(x, y)

    if player_result.get("won"):
        session_data["turn"] = "game_over"
        return HTMLResponse(_render_game_screen(tier_norm, session_data))

    if not player_result.get("repeat"):
        session_data["turn"] = "ai"

        ai_move = ai_opponent.make_move()
        ai_result = ai_game.fire(ai_move.x, ai_move.y)

        ai_opponent.update_game_state(
            ai_move.x,
            ai_move.y,
            hit=ai_result.get("hit", False),
        )

        session_data["last_ai_move"] = ai_move

        if ai_result.get("won"):
            session_data["turn"] = "game_over"
        else:
            session_data["turn"] = "player"

    return HTMLResponse(_render_game_screen(tier_norm, session_data))
