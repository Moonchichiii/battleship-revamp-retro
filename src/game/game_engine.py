"""
Minimal Battleship engine.

Features:
- Configurable board size
- Random fleet placement (size-aware)
- Hit/miss tracking and simple stats
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_BOARD_SIZE = 8
FLEET_CONFIGS: dict[int, list[int]] = {
    6: [3, 2, 2, 1],
    7: [3, 3, 2, 2, 1],
    8: [4, 3, 3, 2, 2],
    9: [4, 4, 3, 3, 2, 1],
    10: [5, 4, 3, 3, 2],
}

Coord = tuple[int, int]


@dataclass
class Game:
    """Holds board state and rules for a single Battleship game."""

    size: int = DEFAULT_BOARD_SIZE
    ships: set[Coord] = field(default_factory=set)
    hits: set[Coord] = field(default_factory=set)
    misses: set[Coord] = field(default_factory=set)

    def is_valid_placement(self: Game, coords: set[Coord]) -> bool:
        """Public wrapper for validating ship placement (used by tests & tools)."""
        return self._is_valid_placement(coords)

    def __post_init__(self: Game) -> None:
        """Validate and clamp board size after initialization."""
        self.size = max(6, min(10, self.size))

    @classmethod
    def new(cls: type[Game], size: int = DEFAULT_BOARD_SIZE) -> Game:
        """Create a game with the given board size and freshly placed fleet."""
        g = cls(size=size)
        g.place_fleet()
        return g

    def reset(self: Game) -> None:
        """Clear shots and re-place the fleet."""
        self.hits.clear()
        self.misses.clear()
        self.ships.clear()
        self.place_fleet()

    @property
    def cells(self: Game) -> list[list[dict[str, bool]]]:
        """Return a 2D grid of cell flags used by the template."""
        grid: list[list[dict[str, bool]]] = [
            [{"hit": False, "miss": False} for _ in range(self.size)]
            for _ in range(self.size)
        ]
        for x, y in self.hits:
            grid[y][x]["hit"] = True
        for x, y in self.misses:
            grid[y][x]["miss"] = True
        return grid

    def fire(self: Game, x: int, y: int) -> dict[str, bool]:
        """Apply a shot; report hit/miss, and if repeated or winning shot."""
        shot = (x, y)
        if shot in self.hits or shot in self.misses:
            return {"repeat": True}
        if shot in self.ships:
            self.hits.add(shot)
            return {"hit": True, "won": self.ships.issubset(self.hits)}
        self.misses.add(shot)
        return {"hit": False}

    def get_fleet_config(self: Game) -> list[int]:
        """Get the fleet configuration for the current board size."""
        return FLEET_CONFIGS.get(self.size, FLEET_CONFIGS[8])

    def get_stats(self: Game) -> dict[str, int | float | bool]:
        """Get current game statistics."""
        shots_fired = len(self.hits) + len(self.misses)
        accuracy = len(self.hits) / shots_fired * 100 if shots_fired > 0 else 0.0
        ships_remaining = len(self.ships) - len(self.hits)
        total_ship_cells = len(self.ships)

        # Calculate percentage of ships remaining
        percent_ships_remaining = (
            ships_remaining / total_ship_cells * 100 if total_ship_cells > 0 else 0.0
        )

        return {
            "shots_fired": shots_fired,
            "hits": len(self.hits),
            "accuracy": round(accuracy, 1),
            "ships_remaining": ships_remaining,
            "total_ship_cells": total_ship_cells,
            "percent_ships_remaining": round(percent_ships_remaining, 1),
            "game_over": self.ships.issubset(self.hits),
            "board_size": self.size,
            "total_cells": self.size * self.size,  # Added for template compatibility
        }

    def place_fleet(self: Game) -> None:
        """Randomly place all ships without overlap or adjacency."""
        self.ships.clear()
        fleet = self.get_fleet_config()

        for length in fleet:
            attempts = 0
            max_attempts = 100

            while attempts < max_attempts:
                horizontal = bool(random.getrandbits(1))
                if horizontal:
                    x = random.randint(0, self.size - length)  # noqa: S311
                    y = random.randint(0, self.size - 1)  # noqa: S311
                    coords = {(x + i, y) for i in range(length)}
                else:
                    x = random.randint(0, self.size - 1)  # noqa: S311
                    y = random.randint(0, self.size - length)  # noqa: S311
                    coords = {(x, y + i) for i in range(length)}

                if self._is_valid_placement(coords):
                    self.ships |= coords
                    break

                attempts += 1

            if attempts >= max_attempts:
                logger.warning(
                    "Could not place ship length %s on %sx%s board",
                    length,
                    self.size,
                    self.size,
                )

    def _is_valid_placement(self: Game, coords: set[Coord]) -> bool:
        """Check if ship placement is valid (no overlap or adjacency)."""
        if coords & self.ships:
            return False

        for x, y in coords:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    adj_x, adj_y = x + dx, y + dy
                    if (adj_x, adj_y) in self.ships:
                        return False

        return True
