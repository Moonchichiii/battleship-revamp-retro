"""HTMX routes for Battleship gameplay with board size selection."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, TypedDict

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.game.game_engine import Game

router = APIRouter()

ROOT = Path(__file__).resolve().parents[3]
templates = Jinja2Templates(directory=str(ROOT / "templates"))


class _State(TypedDict):
    game: Game | None
    size: int


_STATE: _State = {"game": None, "size": 8}


# Helpers
def get_current_game(size: int | None = None) -> Game:
    """Return the current Game instance."""
    game: Game | None = _STATE["game"]
    cur_size: int = _STATE["size"]

    # If no game exists, create with provided size if given; else use current size
    if game is None:
        new_size = size if size is not None else cur_size
        game = Game.new(new_size)
        _STATE["game"] = game
        _STATE["size"] = new_size
        return game

    # If a size is provided and differs, create a new game with that size
    if size is not None and cur_size != size:
        game = Game.new(size)
        _STATE["game"] = game
        _STATE["size"] = size

    return game


def reset_current_game(size: int = 8) -> Game:
    """Reset the current game instance with a new one."""
    game = Game.new(size)
    _STATE["game"] = game
    _STATE["size"] = size
    return game


# Routes
@router.post("/new", response_class=HTMLResponse)
async def new_game(
    request: Request,
    board_size: Annotated[int, Form()] = 8,
) -> HTMLResponse:
    """Create a new game with the specified board size."""
    size = max(6, min(10, board_size))
    game = reset_current_game(size)

    return templates.TemplateResponse(
        request,
        "_board.html",
        {"board": game},
    )


@router.post("/reset", response_class=HTMLResponse)
async def reset_game(
    request: Request,
    board_size: Annotated[int, Form()] = 8,
) -> HTMLResponse:
    """Reset the game with the specified board size."""
    size = max(6, min(10, board_size))
    game = reset_current_game(size)

    return templates.TemplateResponse(
        request,
        "_board.html",
        {"board": game},
    )


@router.post("/shot/{x:int}/{y:int}", response_class=HTMLResponse)
async def shot(
    x: int,
    y: int,
    request: Request,
    board_size: Annotated[int, Form()] = 8,
) -> HTMLResponse:
    """Handle a shot fired at the specified coordinates."""
    size = max(6, min(10, board_size))
    game = get_current_game(size)

    if 0 <= x < game.size and 0 <= y < game.size:
        game.fire(x, y)

    return templates.TemplateResponse(
        request,
        "_board.html",
        {"board": game},
    )


@router.get("/game-status", response_class=HTMLResponse)
async def game_status(request: Request) -> HTMLResponse:
    """Retrieve the current game status."""
    game = get_current_game(_STATE["size"])

    total_cells = game.size * game.size
    shots_fired = sum(
        1 for row in game.cells for cell in row if cell.get("hit") or cell.get("miss")
    )
    hits = sum(1 for row in game.cells for cell in row if cell.get("hit"))
    accuracy = round(hits / shots_fired * 100) if shots_fired > 0 else 0

    status = {
        "shots_fired": shots_fired,
        "hits": hits,
        "accuracy": accuracy,
        "board_size": game.size,
        "total_cells": total_cells,
    }

    return templates.TemplateResponse(
        request,
        "_game_status.html",
        {"status": status},
    )
