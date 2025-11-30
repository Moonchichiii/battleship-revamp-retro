"""Tests for game engine (aligned with current Game implementation)."""

from __future__ import annotations

from src.game.game_engine import DEFAULT_BOARD_SIZE, FLEET_CONFIGS, Game

MIN_BOARD_SIZE = 6
MAX_BOARD_SIZE = 10
MID_BOARD_SIZE = 8
TEST_SIZES = [
    MIN_BOARD_SIZE,
    MIN_BOARD_SIZE + 1,
    MID_BOARD_SIZE,
    MIN_BOARD_SIZE + 3,
    MAX_BOARD_SIZE,
]

THREE_SHIP_CELLS = 3
HUNDRED_PERCENT = 100.0


class TestGame:
    """Test suite for Game class."""

    def test_game_creation_defaults(self) -> None:
        """Test default Game creation."""
        game = Game()
        assert game.size == DEFAULT_BOARD_SIZE
        assert len(game.ships) == 0
        assert len(game.hits) == 0
        assert len(game.misses) == 0

    def test_game_creation_custom_size(self) -> None:
        """Test Game creation with custom size."""
        game = Game(size=MAX_BOARD_SIZE)
        assert game.size == MAX_BOARD_SIZE

    def test_board_size_clamping(self) -> None:
        """Test board size clamping to min/max bounds."""
        game = Game(size=3)
        assert game.size == MIN_BOARD_SIZE

        game = Game(size=15)
        assert game.size == MAX_BOARD_SIZE

        for size in TEST_SIZES:
            game = Game(size=size)
            assert game.size == size

    def test_new_classmethod(self) -> None:
        """Test Game.new classmethod initializes ships."""
        game = Game.new(size=MID_BOARD_SIZE)
        assert game.size == MID_BOARD_SIZE
        assert len(game.ships) > 0

    def test_reset(self) -> None:
        """Test reset restores fresh board with ships."""
        game = Game.new(size=MID_BOARD_SIZE)
        game.hits.add((0, 0))
        game.misses.add((1, 1))

        game.reset()

        assert len(game.hits) == 0
        assert len(game.misses) == 0
        assert len(game.ships) > 0

    def test_get_fleet_config(self) -> None:
        """Test fleet configuration retrieval based on size."""
        for size in TEST_SIZES:
            game = Game(size=size)
            config = game.get_fleet_config()
            assert config == FLEET_CONFIGS[size]

        # size clamps to 10, so config must be MAX_BOARD_SIZE
        game = Game(size=11)
        config = game.get_fleet_config()
        assert config == FLEET_CONFIGS[MAX_BOARD_SIZE]

    def test_cells_property_empty_board(self) -> None:
        """Test cells property on an empty board."""
        game = Game(size=MIN_BOARD_SIZE)
        cells = game.cells

        assert len(cells) == MIN_BOARD_SIZE
        assert len(cells[0]) == MIN_BOARD_SIZE

        for row in cells:
            for cell in row:
                assert cell == {"hit": False, "miss": False}

    def test_cells_property_with_hits_misses(self) -> None:
        """Test cells property reflects hits and misses."""
        game = Game(size=MIN_BOARD_SIZE)
        game.hits.add((1, 2))
        game.misses.add((3, 4))

        cells = game.cells

        assert cells[2][1] == {"hit": True, "miss": False}
        assert cells[4][3] == {"hit": False, "miss": True}
        assert cells[0][0] == {"hit": False, "miss": False}

    def test_fire_hit(self) -> None:
        """Test firing a hit registers correctly."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships.add((2, 3))

        result = game.fire(2, 3)

        assert result["hit"] is True
        assert (2, 3) in game.hits
        assert len(game.misses) == 0

    def test_fire_miss(self) -> None:
        """Test firing a miss registers correctly."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships.discard((0, 0))

        result = game.fire(0, 0)

        assert result["hit"] is False
        assert (0, 0) in game.misses
        assert len(game.hits) == 0

    def test_fire_repeat_shot(self) -> None:
        """Test repeated hit shot is marked as repeat."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships.add((2, 3))

        game.fire(2, 3)
        result = game.fire(2, 3)

        assert result["repeat"] is True

    def test_fire_repeat_miss(self) -> None:
        """Test repeated miss shot is marked as repeat."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships.discard((0, 0))

        game.fire(0, 0)
        result = game.fire(0, 0)

        assert result["repeat"] is True

    def test_fire_winning_shot(self) -> None:
        """Test firing last ship cell reports a win."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships = {(0, 0), (1, 1)}

        result1 = game.fire(0, 0)
        assert result1["hit"] is True
        assert result1.get("won", False) is False

        result2 = game.fire(1, 1)
        assert result2["hit"] is True
        assert result2["won"] is True

    def test_get_stats_empty_game(self) -> None:
        """Test stats for a new empty game."""
        game = Game.new(size=MID_BOARD_SIZE)
        stats = game.get_stats()

        assert stats["shots_fired"] == 0
        assert stats["hits"] == 0
        assert stats["accuracy"] == 0.0
        assert stats["ships_remaining"] == len(game.ships)
        assert stats["total_ship_cells"] == len(game.ships)
        assert stats["percent_ships_remaining"] == HUNDRED_PERCENT
        assert stats["game_over"] is False
        assert stats["board_size"] == MID_BOARD_SIZE
        assert stats["total_cells"] == MID_BOARD_SIZE * MID_BOARD_SIZE

    def test_get_stats_with_shots(self) -> None:
        """Test stats after firing some shots."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships = {(0, 0), (1, 1), (2, 2)}  # 3 ship cells

        # Fire 2 hits and 1 miss
        game.fire(0, 0)  # hit
        game.fire(1, 1)  # hit
        game.fire(5, 5)  # miss

        stats = game.get_stats()

        assert stats["shots_fired"] == 3
        assert stats["hits"] == 2
        assert stats["accuracy"] == round(2 / 3 * 100, 1)  # 66.7%
        assert stats["ships_remaining"] == 1  # 3 - 2 hits
        assert stats["total_ship_cells"] == 3
        assert stats["percent_ships_remaining"] == round(1 / 3 * 100, 1)  # 33.3%
        assert stats["game_over"] is False

    def test_get_stats_game_won(self) -> None:
        """Test stats when game is won."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships = {(0, 0), (1, 1)}  # 2 ship cells

        # Sink all ships
        game.fire(0, 0)  # hit
        game.fire(1, 1)  # hit

        stats = game.get_stats()

        assert stats["shots_fired"] == 2
        assert stats["hits"] == 2
        assert stats["accuracy"] == 100.0
        assert stats["ships_remaining"] == 0
        assert stats["percent_ships_remaining"] == 0.0
        assert stats["game_over"] is True
