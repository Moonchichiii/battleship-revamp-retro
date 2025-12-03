"""Tests for game engine (aligned with current Game implementation)."""

from __future__ import annotations

from src.battleship.game.engine import DEFAULT_BOARD_SIZE, FLEET_CONFIGS, Game

MIN_BOARD_SIZE = 6
MAX_BOARD_SIZE = 10
MID_BOARD_SIZE = 8

class TestGame:
    def test_game_creation_defaults(self) -> None:
        game = Game()
        assert game.size == DEFAULT_BOARD_SIZE
        assert len(game.ships) == 0

    def test_new_classmethod(self) -> None:
        game = Game.new(size=MID_BOARD_SIZE)
        assert game.size == MID_BOARD_SIZE
        assert len(game.ships) > 0

    def test_fire_hit(self) -> None:
        game = Game(size=MID_BOARD_SIZE)
        game.ships.add((2, 3))
        result = game.fire(2, 3)
        assert result["hit"] is True
        assert (2, 3) in game.hits

    def test_fire_miss(self) -> None:
        game = Game(size=MID_BOARD_SIZE)
        result = game.fire(0, 0)
        assert result["hit"] is False
        assert (0, 0) in game.misses