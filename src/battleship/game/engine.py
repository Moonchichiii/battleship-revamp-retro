"""
Minimal Battleship engine.
"""

from __future__ import annotations

import logging
import secrets  # Changed from random to secrets for cryptographic security (S311)
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
        return self._is_valid_placement(coords)

    def __post_init__(self: Game) -> None:
        self.size = max(6, min(10, self.size))

    @classmethod
    def new(cls: type[Game], size: int = DEFAULT_BOARD_SIZE) -> Game:
        g = cls(size=size)
        g.place_fleet()
        return g

    def reset(self: Game) -> None:
        self.hits.clear()
        self.misses.clear()
        self.ships.clear()
        self.place_fleet()

    @property
    def cells(self: Game) -> list[list[dict[str, bool]]]:
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
        shot = (x, y)
        if shot in self.hits or shot in self.misses:
            return {"repeat": True}
        if shot in self.ships:
            self.hits.add(shot)
            return {"hit": True, "won": self.ships.issubset(self.hits)}
        self.misses.add(shot)
        return {"hit": False}

    def get_fleet_config(self: Game) -> list[int]:
        return FLEET_CONFIGS.get(self.size, FLEET_CONFIGS[8])

    def get_stats(self: Game) -> dict[str, int | float | bool]:
        shots_fired = len(self.hits) + len(self.misses)
        accuracy = len(self.hits) / shots_fired * 100 if shots_fired > 0 else 0.0
        ships_remaining = len(self.ships) - len(self.hits)
        total_ship_cells = len(self.ships)
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
            "total_cells": self.size * self.size,
        }

    def place_fleet(self: Game) -> None:
        self.ships.clear()
        fleet = self.get_fleet_config()
        for length in fleet:
            attempts = 0
            max_attempts = 100
            while attempts < max_attempts:
                # Use secrets for cryptographically secure random choice
                horizontal = secrets.choice([True, False])

                if horizontal:
                    # secrets.randbelow(n) returns 0 to n-1
                    # Range needed: 0 to self.size - length (inclusive)
                    x_limit = self.size - length + 1
                    y_limit = self.size

                    x = secrets.randbelow(x_limit)
                    y = secrets.randbelow(y_limit)
                    coords = {(x + i, y) for i in range(length)}
                else:
                    x_limit = self.size
                    y_limit = self.size - length + 1

                    x = secrets.randbelow(x_limit)
                    y = secrets.randbelow(y_limit)
                    coords = {(x, y + i) for i in range(length)}

                if self._is_valid_placement(coords):
                    self.ships |= coords
                    break
                attempts += 1

    def _is_valid_placement(self: Game, coords: set[Coord]) -> bool:
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
