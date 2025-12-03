"""LLM-powered AI opponent for Battleship that uses external language model APIs to select moves."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

import anyio
import httpx

if TYPE_CHECKING:
    from src.battleship.game.engine import Game

from src.battleship.ai.strategies import AIMove, BattleshipAI


class LLMAIOpponent(BattleshipAI):
    """AI opponent using a language model for decision making."""

    def __init__(self, game: Game, api_key: str) -> None:
        """Initialize LLM AI opponent with game instance and API key."""
        super().__init__(game)
        self.api_key = api_key

    def make_move(self) -> AIMove:
        """Return the AI's next move."""
        return anyio.run(self._make_move_async)

    async def _make_move_async(self) -> AIMove:
        prompt = self._create_game_prompt()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a Battleship AI opponent. Respond with only "
                                "coordinates in format 'x,y' followed by a brief strategy explanation."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 100,
                    "temperature": 0.7,
                },
            )

        return self._parse_llm_response(response.json())

    def _create_game_prompt(self) -> str:
        """Create prompt describing current game state."""
        available_moves = [
            (x, y)
            for x in range(self.game.size)
            for y in range(self.game.size)
            if (x, y) not in self.previous_moves
        ]

        return f"""
Current Battleship game state:
- Board size: {self.game.size}x{self.game.size}
- My previous moves: {self.previous_moves[-10:]}
- My hits: {self.hits}
- High priority targets: {self.hunt_targets}
- Available moves: {len(available_moves)} remaining

Choose your next move as coordinates (x, y) between 0 and {self.game.size-1}.
Format: "x,y - strategy explanation"
Focus on logical ship placement patterns and hunting damaged ships.
        """.strip()

    def _parse_llm_response(self, response_data: dict[str, Any]) -> AIMove:
        """Parse LLM JSON response into AIMove object."""
        try:
            content = response_data["choices"][0]["message"]["content"].strip()

            if " - " in content:
                coords_part, reasoning = content.split(" - ", 1)
            else:
                coords_part = content.split()[0] if content else "0,0"
                reasoning = "LLM decision"

            if "," in coords_part:
                x_str, y_str = coords_part.split(",", 1)
                x = int(x_str.strip())
                y = int(y_str.strip())
            else:
                parts = coords_part.replace("(", "").replace(")", "").split()
                x = int(parts[0]) if len(parts) > 0 else 0
                y = int(parts[1]) if len(parts) > 1 else 0

            if not (0 <= x < self.game.size and 0 <= y < self.game.size):
                return self._fallback_move("Invalid coordinates from LLM")

            if (x, y) in self.previous_moves:
                return self._fallback_move("LLM chose already played position")

            return AIMove(
                x=x,
                y=y,
                confidence=0.85,
                reasoning=reasoning.strip()[:100],
            )

        except (KeyError, ValueError, IndexError) as e:
            return self._fallback_move(f"Failed to parse LLM response: {e}")

    def _fallback_move(self, reason: str) -> AIMove:
        """Generate fallback move when LLM parsing fails."""
        if self.hunt_targets:
            target = self.hunt_targets.pop(0)
            return AIMove(
                x=target[0],
                y=target[1],
                confidence=0.6,
                reasoning=f"Fallback hunt target ({reason})",
            )

        available = [
            (x, y)
            for x in range(self.game.size)
            for y in range(self.game.size)
            if (x, y) not in self.previous_moves
        ]

        if available:
            import secrets

            target = secrets.choice(available)
            return AIMove(
                x=target[0],
                y=target[1],
                confidence=0.3,
                reasoning=f"Random fallback ({reason})",
            )

        return AIMove(
            x=0,
            y=0,
            confidence=0.1,
            reasoning=f"Emergency fallback ({reason})",
        )


class AiOpponent:
    """Rule-based AI opponent with three difficulty tiers for HTMX flows."""

    def __init__(self, game: Game) -> None:
        self.game = game

    def get_legal_moves(self) -> list[tuple[int, int]]:
        """Return all untried coordinates."""
        tried = self.game.hits | self.game.misses
        return [
            (x, y)
            for x in range(self.game.size)
            for y in range(self.game.size)
            if (x, y) not in tried
        ]

    def get_best_move(self, difficulty: str) -> tuple[int, int]:
        """Select a move based on difficulty."""
        difficulty = (difficulty or "novice").lower()
        if difficulty == "intermediate":
            move = self._intermediate_move()
        elif difficulty == "expert":
            move = self._expert_move()
        else:
            move = self._novice_move()

        return move or self._fallback()

    def _novice_move(self) -> tuple[int, int] | None:
        """Random legal move with slight edge preference."""
        moves = self.get_legal_moves()
        if not moves:
            return None

        edge_cells = [
            m
            for m in moves
            if m[0] in (0, self.game.size - 1) or m[1] in (0, self.game.size - 1)
        ]
        pool = edge_cells or moves
        return random.choice(pool)  # noqa: S311

    def _intermediate_move(self) -> tuple[int, int] | None:
        """Hunt near hits; otherwise use checkerboard parity."""
        moves = self.get_legal_moves()
        if not moves:
            return None

        for hx, hy in list(self.game.hits):
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = hx + dx, hy + dy
                if (nx, ny) in moves:
                    return (nx, ny)

        parity_moves = [(x, y) for (x, y) in moves if (x + y) % 2 == 0]
        if parity_moves:
            return random.choice(parity_moves)  # noqa: S311

        return random.choice(moves)  # noqa: S311

    def _expert_move(self) -> tuple[int, int] | None:
        """Probability-based targeting."""
        moves = self.get_legal_moves()
        if not moves:
            return None

        ship_sizes = self._remaining_ship_sizes()
        scores: dict[tuple[int, int], int] = {m: 0 for m in moves}

        for size in ship_sizes:
            for y in range(self.game.size):
                for x in range(self.game.size - size + 1):
                    coords = {(x + i, y) for i in range(size)}
                    if self._placement_conflicts(coords):
                        continue
                    for c in coords & set(moves):
                        scores[c] += 1

            for x in range(self.game.size):
                for y in range(self.game.size - size + 1):
                    coords = {(x, y + i) for i in range(size)}
                    if self._placement_conflicts(coords):
                        continue
                    for c in coords & set(moves):
                        scores[c] += 1

        max_score = max(scores.values()) if scores else 0
        candidates = [cell for cell, score in scores.items() if score == max_score]
        if candidates:
            return random.choice(candidates)  # noqa: S311

        return random.choice(moves)  # noqa: S311

    def _placement_conflicts(self, coords: set[tuple[int, int]]) -> bool:
        """Reject placements that hit misses or skip required hits."""
        if coords & self.game.misses:
            return True
        if self.game.hits and not self.game.hits.issubset(coords | self.game.misses):
            hits_in_line = self.game.hits & coords
            if hits_in_line:
                return False
        return False

    def _remaining_ship_sizes(self) -> list[int]:
        """Estimate remaining ships based on board size and hits."""
        from src.battleship.game.engine import FLEET_CONFIGS

        fleet = FLEET_CONFIGS.get(self.game.size, FLEET_CONFIGS[8])
        sunk_hits = len(self.game.hits)
        remaining = list(fleet)
        while sunk_hits > 0 and remaining:
            smallest = min(remaining)
            remaining.remove(smallest)
            sunk_hits -= smallest
        return remaining or [2]

    def _fallback(self) -> tuple[int, int]:
        """Choose a deterministic fallback move."""
        moves = self.get_legal_moves()
        return moves[0] if moves else (0, 0)
