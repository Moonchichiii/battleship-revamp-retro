"""AI opponents for Battleship with different difficulty levels."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.game.engine import Game

# Constants for AI behavior tuning
ROOKIE_HUNT_CHANCE = 0.3
CHECKERBOARD_OFFSET = 2


@dataclass
class AIMove:
    """Represents an AI move decision."""

    x: int
    y: int
    confidence: float
    reasoning: str


class BattleshipAI(ABC):
    """Abstract base class for AI opponents."""

    # Track accuracy as a float (may be computed as a float elsewhere)
    accuracy: float

    def __init__(self, game: Game) -> None:
        """Initialize AI opponent with game instance."""
        self.game = game
        self.previous_moves: list[tuple[int, int]] = []
        self.hits: list[tuple[int, int]] = []
        self.hunt_targets: list[tuple[int, int]] = []
        self.accuracy: float = 0.0

    @abstractmethod
    def make_move(self) -> AIMove:
        """Make the next move."""

    def update_game_state(self, x: int, y: int, *, hit: bool) -> None:
        """Update AI's knowledge of game state."""
        self.previous_moves.append((x, y))
        if hit:
            self.hits.append((x, y))
            self._add_adjacent_targets(x, y)

    def _add_adjacent_targets(self, x: int, y: int) -> None:
        """Add adjacent cells as high-priority targets."""
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if (
                0 <= nx < self.game.size
                and 0 <= ny < self.game.size
                and (nx, ny) not in self.previous_moves
                and (nx, ny) not in self.hunt_targets
            ):
                self.hunt_targets.append((nx, ny))


class RookieAI(BattleshipAI):
    """Easy AI - mostly random with basic hit follow-up."""

    def make_move(self) -> AIMove:
        """Make a move using basic strategy with low hunt probability."""
        # Low chance to use hunt targets if available
        if self.hunt_targets and random.random() < ROOKIE_HUNT_CHANCE:  # noqa: S311
            target = self.hunt_targets.pop(0)
            return AIMove(
                x=target[0],
                y=target[1],
                confidence=0.6,
                reasoning="Following up on previous hit",
            )

        # Otherwise random move
        available = [
            (x, y)
            for x in range(self.game.size)
            for y in range(self.game.size)
            if (x, y) not in self.previous_moves
        ]

        if not available:
            # Fallback
            return AIMove(x=0, y=0, confidence=0.1, reasoning="No moves available")

        target = random.choice(available)  # noqa: S311
        return AIMove(
            x=target[0],
            y=target[1],
            confidence=0.3,
            reasoning="Random guess",
        )


class VeteranAI(BattleshipAI):
    """Medium AI - uses checkerboard pattern + hunt mode."""

    def make_move(self) -> AIMove:
        """Make a move using checkerboard pattern and aggressive hunting."""
        # Always prioritize hunt targets
        if self.hunt_targets:
            target = self.hunt_targets.pop(0)
            return AIMove(
                x=target[0],
                y=target[1],
                confidence=0.8,
                reasoning="Hunting damaged ship",
            )

        # Use checkerboard pattern for efficiency
        available = [
            (x, y)
            for x in range(self.game.size)
            for y in range(self.game.size)
            if (x, y) not in self.previous_moves
        ]

        # Prefer checkerboard squares (ships need 2+ adjacent cells)
        checkerboard = [
            (x, y) for x, y in available if (x + y) % CHECKERBOARD_OFFSET == 0
        ]

        if checkerboard:
            target = random.choice(checkerboard)  # noqa: S311
            return AIMove(
                x=target[0],
                y=target[1],
                confidence=0.6,
                reasoning="Checkerboard pattern search",
            )

        if available:
            target = random.choice(available)  # noqa: S311
            return AIMove(
                x=target[0],
                y=target[1],
                confidence=0.4,
                reasoning="Filling remaining spaces",
            )

        return AIMove(x=0, y=0, confidence=0.1, reasoning="No moves available")


class AdmiralAI(BattleshipAI):
    """Hard AI - advanced probability-based targeting."""

    def __init__(self, game: Game) -> None:
        """Initialize Admiral AI with probability mapping."""
        super().__init__(game)
        self.probability_map = [
            [1.0 for _ in range(game.size)] for _ in range(game.size)
        ]
        self.ship_sizes = [5, 4, 3, 3, 2]  # Common ship sizes

    def make_move(self) -> AIMove:
        """Make a move using advanced probability-based targeting."""
        # Update probability map
        self._update_probabilities()

        # Always prioritize hunt targets with probability weighting
        if self.hunt_targets:
            # Sort hunt targets by probability
            self.hunt_targets.sort(
                key=lambda pos: self.probability_map[pos[1]][pos[0]],
                reverse=True,
            )
            target = self.hunt_targets.pop(0)
            return AIMove(
                x=target[0],
                y=target[1],
                confidence=0.9,
                reasoning="High-probability hunt target",
            )

        # Find highest probability cell
        max_prob = 0.0
        best_targets = []

        for y in range(self.game.size):
            for x in range(self.game.size):
                if (x, y) not in self.previous_moves:
                    prob = self.probability_map[y][x]
                    if prob > max_prob:
                        max_prob = prob
                        best_targets = [(x, y)]
                    elif prob == max_prob:
                        best_targets.append((x, y))

        if best_targets:
            target = random.choice(best_targets)  # noqa: S311
            return AIMove(
                x=target[0],
                y=target[1],
                confidence=min(0.95, max_prob),
                reasoning=f"Highest probability target ({max_prob:.2f})",
            )

        return AIMove(x=0, y=0, confidence=0.1, reasoning="No moves available")

    def _update_probabilities(self) -> None:
        """Update probability map based on game state."""
        # Reset probabilities
        for y in range(self.game.size):
            for x in range(self.game.size):
                if (x, y) in self.previous_moves:
                    self.probability_map[y][x] = 0.0
                else:
                    self.probability_map[y][x] = 1.0

        # Increase probabilities near hits
        for hx, hy in self.hits:
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = hx + dx, hy + dy
                if (
                    0 <= nx < self.game.size
                    and 0 <= ny < self.game.size
                    and (nx, ny) not in self.previous_moves
                ):
                    self.probability_map[ny][nx] *= 2.0


def create_ai(tier: str, game: Game, **kwargs: str) -> BattleshipAI:
    """Create appropriate AI instance based on tier."""
    ai_classes: dict[str, type[BattleshipAI]] = {
        "rookie": RookieAI,
        "veteran": VeteranAI,
        "admiral": AdmiralAI,
    }

    # Check for LLM tier (requires api_key)
    if tier == "llm" and "api_key" in kwargs:
        try:
            from src.ai.ai_opponent import LLMAIOpponent

            return LLMAIOpponent(game, kwargs["api_key"])
        except ImportError:
            # Fallback to Admiral if LLM dependencies not available
            return AdmiralAI(game)

    ai_class = ai_classes.get(tier, RookieAI)
    return ai_class(game)
