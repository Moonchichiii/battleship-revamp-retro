"""Scores routes and database models for user game scoring."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.battleship.core.database import Base

if TYPE_CHECKING:
    from src.battleship.users.models import (
        AuthService,
        User,
        get_auth_service,
        optional_authenticated_user,
    )

router = APIRouter()

ROOT = Path(__file__).resolve().parents[3]
templates = Jinja2Templates(directory=str(ROOT / "templates"))


class Score(Base):
    """User game scores table."""

    __tablename__ = "scores"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    shots_fired: Mapped[int] = mapped_column(Integer, nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    board_size: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str] = mapped_column(
        String(20),
        default='standard',
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="scores")


class ScoreService:
    """Service for managing game scores."""

    def __init__(self, auth_service: AuthService) -> None:
        self.auth_service = auth_service
        self.db = auth_service.db

    def create_score(
        self,
        user_id: uuid.UUID,
        score: int,
        shots_fired: int,
        accuracy: float,
        board_size: int,
        difficulty: str = "standard",
    ) -> Score:
        """Create a new score record."""
        score_record = Score(
            user_id=user_id,
            score=score,
            shots_fired=shots_fired,
            accuracy=accuracy,
            board_size=board_size,
            difficulty=difficulty,
        )
        self.db.add(score_record)
        self.db.commit()
        self.db.refresh(score_record)
        return score_record

    def get_top_scores(self, limit: int = 10, board_size: int = 8) -> list[dict[str, Any]]:
        """Get top scores using composite index (board_size, score, shots)."""
        from src.battleship.users.models import User

        stmt = (
            select(Score, User)
            .join(User, Score.user_id == User.id)
            .filter(User.is_active == True)  # noqa: E712
            .filter(Score.board_size == board_size)
            .order_by(Score.score.desc(), Score.shots_fired.asc())
            .limit(limit)
        )

        results = self.db.execute(stmt).all()

        scores = []
        for score_record, user in results:
            scores.append(
                {
                    "player_name": user.display_name or user.username,
                    "score": score_record.score,
                    "created_at": score_record.created_at,
                    "shots_fired": score_record.shots_fired,
                    "accuracy": score_record.accuracy,
                    "board_size": score_record.board_size,
                    "difficulty": score_record.difficulty,
                },
            )
        return scores

    def get_user_scores(self, user_id: uuid.UUID, limit: int = 5) -> list[Score]:
        """Get a user's recent scores."""
        stmt = (
            select(Score)
            .filter(Score.user_id == user_id)
            .order_by(Score.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_user_best_score(self, user_id: uuid.UUID, board_size: int = 8) -> Score | None:
        """Get a user's absolute best score."""
        stmt = (
            select(Score)
            .filter(Score.user_id == user_id)
            .filter(Score.board_size == board_size)
            .order_by(Score.score.desc(), Score.shots_fired.asc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_user_rank(self, user_id: uuid.UUID, board_size: int = 8) -> int | None:
        """Calculate user's rank using a window function."""
        subq = (
            select(
                Score.user_id,
                func.rank().over(
                    order_by=[Score.score.desc(), Score.shots_fired.asc()]
                ).label("rank")
            )
            .filter(Score.board_size == board_size)
            .subquery()
        )

        stmt = (
            select(subq.c.rank)
            .filter(subq.c.user_id == user_id)
            .limit(1)
        )

        return self.db.execute(stmt).scalar_one_or_none()


def get_score_service(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> ScoreService:
    return ScoreService(auth_service)


@router.get("/scores", response_class=HTMLResponse)
async def scores_page(
    request: Request,
    current_user: Annotated[User | None, Depends(optional_authenticated_user)],
    score_service: Annotated[ScoreService, Depends(get_score_service)],
) -> HTMLResponse:
    """Display the scores page with top scores."""
    top_scores = score_service.get_top_scores(limit=20, board_size=8)

    context = {
        "current_user": current_user,
        "scores": top_scores,
        "offset": 0,
    }
    return templates.TemplateResponse(request, "scores.html", context)


@router.get("/api/scores/top", response_class=HTMLResponse)
async def api_top_scores(
    request: Request,
    score_service: Annotated[ScoreService, Depends(get_score_service)],
    limit: int = 10,
    board_size: int = 8,
) -> HTMLResponse:
    """Fetch top scores table body for HTMX."""
    top_scores = score_service.get_top_scores(limit=limit, board_size=board_size)

    context = {
        "scores": top_scores,
        "offset": 0,
    }
    return templates.TemplateResponse(request, "_scores_tbody.html", context)


def save_game_score(
    user_id: uuid.UUID,
    game_stats: dict[str, Any],
    score_service: ScoreService,
) -> Score:
    """Save a completed game score."""
    base_score = 1000
    shot_penalty = game_stats["shots_fired"] * 10
    accuracy_bonus = int(game_stats["accuracy"] * 2)
    size_bonus = game_stats["board_size"] * 5

    final_score = max(0, base_score - shot_penalty + accuracy_bonus + size_bonus)
    difficulty = game_stats.get("difficulty", "standard")

    return score_service.create_score(
        user_id=user_id,
        score=final_score,
        shots_fired=game_stats["shots_fired"],
        accuracy=game_stats["accuracy"],
        board_size=game_stats["board_size"],
        difficulty=difficulty,
    )
