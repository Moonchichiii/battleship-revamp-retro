"""Tests for game engine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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

TWO_SHIP_CELLS = 2
THREE_SHIP_CELLS = 3
HUNDRED_PERCENT = 100.0


class TestGame:  # pylint: disable=too-many-public-methods
    """Test suite for Game class."""

    def test_game_creation_defaults(self: TestGame) -> None:
        """Test game creation with default values."""
        game = Game()
        assert game.size == DEFAULT_BOARD_SIZE
        assert len(game.ships) == 0
        assert len(game.hits) == 0
        assert len(game.misses) == 0

    def test_game_creation_custom_size(self: TestGame) -> None:
        """Test game creation with custom board size."""
        game = Game(size=MAX_BOARD_SIZE)
        assert game.size == MAX_BOARD_SIZE

    def test_board_size_clamping(self: TestGame) -> None:
        """Test that board size is clamped to valid range."""
        game = Game(size=3)
        assert game.size == MIN_BOARD_SIZE

        game = Game(size=15)
        assert game.size == MAX_BOARD_SIZE

        for size in TEST_SIZES:
            game = Game(size=size)
            assert game.size == size

    def test_new_classmethod(self: TestGame) -> None:
        """Test Game.new() creates game with placed fleet."""
        game = Game.new(size=MID_BOARD_SIZE)
        assert game.size == MID_BOARD_SIZE
        assert len(game.ships) > 0

    def test_reset(self: TestGame) -> None:
        """Test game reset clears state and replaces fleet."""
        game = Game.new(size=MID_BOARD_SIZE)
        game.hits.add((0, 0))
        game.misses.add((1, 1))

        game.reset()

        assert len(game.hits) == 0
        assert len(game.misses) == 0
        assert len(game.ships) > 0

    def test_get_fleet_config(self: TestGame) -> None:
        """Test fleet configuration for different board sizes."""
        for size in TEST_SIZES:
            game = Game(size=size)
            config = game.get_fleet_config()
            assert config == FLEET_CONFIGS[size]

        game = Game(size=11)
        config = game.get_fleet_config()
        assert config == FLEET_CONFIGS[MAX_BOARD_SIZE]

    def test_cells_property_empty_board(self: TestGame) -> None:
        """Test cells property with empty board."""
        game = Game(size=MIN_BOARD_SIZE)
        cells = game.cells

        assert len(cells) == MIN_BOARD_SIZE
        assert len(cells[0]) == MIN_BOARD_SIZE

        for row in cells:
            for cell in row:
                assert cell == {"hit": False, "miss": False}

    def test_cells_property_with_hits_misses(self: TestGame) -> None:
        """Test cells property with hits and misses."""
        game = Game(size=MIN_BOARD_SIZE)
        game.hits.add((1, 2))
        game.misses.add((3, 4))

        cells = game.cells

        assert cells[2][1] == {"hit": True, "miss": False}
        assert cells[4][3] == {"hit": False, "miss": True}
        assert cells[0][0] == {"hit": False, "miss": False}

    def test_fire_hit(self: TestGame) -> None:
        """Test firing at a ship."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships.add((2, 3))

        result = game.fire(2, 3)

        assert result["hit"] is True
        assert (2, 3) in game.hits
        assert len(game.misses) == 0

    def test_fire_miss(self: TestGame) -> None:
        """Test firing and missing."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships.discard((0, 0))

        result = game.fire(0, 0)

        assert result["hit"] is False
        assert (0, 0) in game.misses
        assert len(game.hits) == 0

    def test_fire_repeat_shot(self: TestGame) -> None:
        """Test firing at same location twice."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships.add((2, 3))

        game.fire(2, 3)
        result = game.fire(2, 3)

        assert result["repeat"] is True

    def test_fire_repeat_miss(self: TestGame) -> None:
        """Test firing at same miss location twice."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships.discard((0, 0))

        game.fire(0, 0)
        result = game.fire(0, 0)

        assert result["repeat"] is True

    def test_fire_winning_shot(self: TestGame) -> None:
        """Test winning the game with final shot."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships = {(0, 0), (1, 1)}

        result1 = game.fire(0, 0)
        assert result1["hit"] is True
        assert "won" not in result1 or result1["won"] is False

        result2 = game.fire(1, 1)
        assert result2["hit"] is True
        assert result2["won"] is True

    def test_get_stats_empty_game(self: TestGame) -> None:
        """Test stats for new game."""
        game = Game.new(size=MID_BOARD_SIZE)
        stats = game.get_stats()

        assert stats["shots_fired"] == 0
        assert stats["hits"] == 0
        assert stats["accuracy"] == 0.0
        assert stats["ships_remaining"] == len(game.ships)
        assert stats["total_ship_cells"] == len(game.ships)
        assert stats["game_over"] is False
        assert stats["board_size"] == MID_BOARD_SIZE

    def test_get_stats_with_shots(self: TestGame) -> None:
        """Test stats with some shots fired."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships = {(0, 0), (1, 1), (2, 2)}

        game.fire(0, 0)
        game.fire(5, 5)
        game.fire(6, 6)

        stats = game.get_stats()

        expected_shots = 3
        expected_hits = 1
        expected_accuracy = round(expected_hits / expected_shots * 100, 1)

        assert stats["shots_fired"] == expected_shots
        assert stats["hits"] == expected_hits
        assert stats["accuracy"] == expected_accuracy
        assert stats["ships_remaining"] == THREE_SHIP_CELLS - expected_hits
        assert stats["total_ship_cells"] == THREE_SHIP_CELLS
        assert stats["game_over"] is False

    def test_get_stats_won_game(self: TestGame) -> None:
        """Test stats for completed game."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships = {(0, 0), (1, 1)}

        game.fire(0, 0)
        game.fire(1, 1)

        stats = game.get_stats()

        assert stats["game_over"] is True
        assert stats["ships_remaining"] == 0
        assert stats["accuracy"] == HUNDRED_PERCENT

    def test_place_fleet(self: TestGame) -> None:
        """Test fleet placement."""
        game = Game(size=MID_BOARD_SIZE)
        game.place_fleet()

        assert len(game.ships) > 0

        for x, y in game.ships:
            assert 0 <= x < game.size
            assert 0 <= y < game.size

    def test_place_fleet_different_sizes(self: TestGame) -> None:
        """Test fleet placement for different board sizes."""
        for size in TEST_SIZES:
            game = Game(size=size)
            game.place_fleet()

            expected_config = FLEET_CONFIGS[size]
            expected_total = sum(expected_config)

            assert len(game.ships) <= expected_total
            assert len(game.ships) > 0

    @patch("src.game.game_engine.random.randint")
    @patch("src.game.game_engine.random.getrandbits")
    def test_place_fleet_placement_failure(
        self: TestGame,
        mock_getrandbits: MagicMock,
        mock_randint: MagicMock,
    ) -> None:
        """Test fleet placement when it can't place all ships."""
        game = Game(size=MIN_BOARD_SIZE)

        mock_randint.return_value = 0
        mock_getrandbits.return_value = 1

        with patch("src.game.game_engine.logger") as mock_logger:
            game.place_fleet()
            assert mock_logger.warning.called

    def test_is_valid_placement_no_overlap(self: TestGame) -> None:
        """Test valid placement check â€” no overlapping ships."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships = {(0, 0), (1, 0)}

        new_coords = {(1, 0), (2, 0)}

        assert not game.is_valid_placement(new_coords)

    def test_is_valid_placement_no_adjacency(self: TestGame) -> None:
        """Test valid placement check â€” no side adjacency."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships = {(2, 2)}

        adjacent_coords = {(3, 2)}

        assert not game.is_valid_placement(adjacent_coords)

    def test_is_valid_placement_diagonal_adjacency(self: TestGame) -> None:
        """Test valid placement check â€” no diagonal adjacency."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships = {(2, 2)}

        diagonal_coords = {(3, 3)}

        assert not game.is_valid_placement(diagonal_coords)

    def test_is_valid_placement_valid(self: TestGame) -> None:
        """Test valid placement check â€” valid placement."""
        game = Game(size=MID_BOARD_SIZE)
        game.ships = {(0, 0)}

        valid_coords = {(5, 5), (6, 5)}

        assert game.is_valid_placement(valid_coords)
