"""Tests for game engine (Standard 8x8 Board)."""

from __future__ import annotations

from src.battleship.game.engine import DEFAULT_BOARD_SIZE, Game

STANDARD_SIZE = 8


class TestGame:
    def test_game_creation_defaults(self) -> None:
        """Test default Game creation uses standard size."""
        game = Game()
        assert game.size == DEFAULT_BOARD_SIZE
        assert game.size == STANDARD_SIZE
        assert len(game.ships) == 0

    def test_new_classmethod(self) -> None:
        """Test Game.new creates a populated board."""
        game = Game.new(size=STANDARD_SIZE)
        assert game.size == STANDARD_SIZE
        assert len(game.ships) > 0

    def test_fire_hit(self) -> None:
        """Test firing a shot that hits a ship."""
        game = Game(size=STANDARD_SIZE)
        test_coord = (2, 3)
        game.ships.add(test_coord)

        result = game.fire(*test_coord)

        assert result["hit"] is True
        assert test_coord in game.hits
        assert test_coord not in game.misses

    def test_fire_miss(self) -> None:
        """Test firing a shot into empty water."""
        game = Game(size=STANDARD_SIZE)
        test_coord = (0, 0)
        game.ships.discard(test_coord)

        result = game.fire(*test_coord)

        assert result["hit"] is False
        assert test_coord in game.misses
        assert test_coord not in game.hits

    def test_fire_repeat(self) -> None:
        """Test firing at the same coordinate twice."""
        game = Game(size=STANDARD_SIZE)
        test_coord = (4, 4)

        game.fire(*test_coord)
        result = game.fire(*test_coord)

        assert result.get("repeat") is True
