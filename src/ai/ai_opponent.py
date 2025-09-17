"""LLM-powered AI opponent for Battleship that uses external language model APIs to select moves."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anyio
import httpx

if TYPE_CHECKING:
    from src.game.game_engine import Game

from src.ai.battleship_ai import AIMove, BattleshipAI


class LLMAIOpponent(BattleshipAI):
    """AI opponent using a language model for decision making."""

    def __init__(self, game: Game, api_key: str) -> None:
        """Initialize LLM AI opponent with game instance and API key."""
        super().__init__(game)
        self.api_key = api_key

    def make_move(self) -> AIMove:
        """Return the AI's next move."""
        return anyio.run(self._make_move_async)

    # keep your actual LLM call async
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

        # Parse LLM response into move coordinates
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
- My previous moves: {self.previous_moves[-10:]}  # Last 10 moves
- My hits: {self.hits}
- High priority targets: {self.hunt_targets}
- Available moves: {len(available_moves)} remaining

Choose your next move as coordinates (x, y) between 0 and {self.game.size-1}.
Format: "x,y - strategy explanation"
Focus on logical ship placement patterns and hunting damaged ships.
        """.strip()

    # <-- add concrete type params for dict
    def _parse_llm_response(self, response_data: dict[str, Any]) -> AIMove:
        """Parse LLM JSON response into AIMove object."""
        try:
            content = response_data["choices"][0]["message"]["content"].strip()

            # Expected format: "x,y - explanation"
            if " - " in content:
                coords_part, reasoning = content.split(" - ", 1)
            else:
                coords_part = content.split()[0] if content else "0,0"
                reasoning = "LLM decision"

            # Parse coordinates
            if "," in coords_part:
                x_str, y_str = coords_part.split(",", 1)
                x = int(x_str.strip())
                y = int(y_str.strip())
            else:
                # Fallback parsing
                parts = coords_part.replace("(", "").replace(")", "").split()
                x = int(parts[0]) if len(parts) > 0 else 0
                y = int(parts[1]) if len(parts) > 1 else 0

            # Validate coordinates
            if not (0 <= x < self.game.size and 0 <= y < self.game.size):
                return self._fallback_move("Invalid coordinates from LLM")

            # Check if already played
            if (x, y) in self.previous_moves:
                return self._fallback_move("LLM chose already played position")

            return AIMove(
                x=x,
                y=y,
                confidence=0.85,
                reasoning=reasoning.strip()[:100],  # Limit reasoning length
            )

        except (KeyError, ValueError, IndexError) as e:
            return self._fallback_move(f"Failed to parse LLM response: {e}")

    def _fallback_move(self, reason: str) -> AIMove:
        """Generate fallback move when LLM parsing fails."""
        # Use hunt targets if available
        if self.hunt_targets:
            target = self.hunt_targets.pop(0)
            return AIMove(
                x=target[0],
                y=target[1],
                confidence=0.6,
                reasoning=f"Fallback hunt target ({reason})",
            )

        # Random available move
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

        # Ultimate fallback
        return AIMove(
            x=0,
            y=0,
            confidence=0.1,
            reasoning=f"Emergency fallback ({reason})",
        )
