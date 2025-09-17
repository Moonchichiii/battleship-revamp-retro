"""Auth models and helpers for PostgreSQL-backed users/sessions."""

from __future__ import annotations

import os
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from src.api.core.database import TESTING, Base, get_db
from src.api.core.security import verify_token

if TYPE_CHECKING:
    from src.api.routes.scores_routes import Score

security = HTTPBearer(auto_error=False)

# -------------------------
# ORM models (SQLAlchemy 2.0 typed)
# -------------------------


class User(Base):
    """Users table."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    github_id: Mapped[int | None] = mapped_column(
        Integer,
        unique=True,
        index=True,
    )
    display_name: Mapped[str | None] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    scores: Mapped[list[Score]] = relationship(
        "Score",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserSession(Base):
    """Session tokens for web clients."""

    __tablename__ = "user_sessions"

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
    session_token: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    # FIXED: Always use String(45) to match database schema
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    user: Mapped[User] = relationship(back_populates="sessions")


# -------------------------
# Pydantic models
# -------------------------


class UserResponse(BaseModel):
    """Public user fields."""

    id: str
    username: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    is_active: bool
    is_verified: bool
    last_login: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthenticatedUser(BaseModel):
    """Current auth context."""

    id: str
    username: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    is_active: bool
    is_verified: bool
    permissions: list[str] = Field(default_factory=list)


# -------------------------
# Service + deps
# -------------------------

_rate_limit_store: dict[str, list[float]] = {}


class AuthService:
    """User, session, and rate-limit helpers."""

    def __init__(self, db: Session, secret_key: str) -> None:
        """Initialize the AuthService."""
        self.db = db
        self.secret_key = secret_key

    def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email (case-insensitive)."""
        return self.db.query(User).filter(User.email == email.lower()).first()

    def get_user_by_id(self, user_id: str) -> User | None:
        """Get a user by UUID string."""
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            return None
        return self.db.query(User).filter(User.id == user_uuid).first()

    def get_user_by_username(self, username: str) -> User | None:
        """Get a user by username."""
        return self.db.query(User).filter(User.username == username).first()

    def get_user_by_github_id(self, github_id: int) -> User | None:
        """Get a user by GitHub ID."""
        return self.db.query(User).filter(User.github_id == github_id).first()

    def create_user(
        self,
        email: str,
        password_hash: str,
        username: str | None = None,
    ) -> User:
        """Create a normal (email/password) user."""
        if not username:
            # Extract base username from email local part, handling test cases
            local_part = email.split("@")[0]
            # For test emails like "test+uuid@example.com", use just "test"
            username = local_part.split("+")[0] if "+" in local_part else local_part

        # Ensure username uniqueness
        base = username
        i = 1
        while self.get_user_by_username(username):
            username = f"{base}{i}"
            i += 1

        user = User(
            email=email.lower(),
            username=username,
            password_hash=password_hash,
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def create_oauth_user(
        self,
        email: str,
        github_id: int,
        username: str,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        """Create a user from OAuth (GitHub) info."""
        base = username
        i = 1
        while self.get_user_by_username(username):
            username = f"{base}{i}"
            i += 1

        user = User(
            email=email.lower(),
            username=username,
            github_id=github_id,
            display_name=display_name,
            avatar_url=avatar_url,
            is_active=True,
            is_verified=True,
            password_hash=None,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_user_oauth_info(
        self,
        user: User,
        github_id: int,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        """Update a user's OAuth metadata."""
        if not user.github_id:
            user.github_id = github_id
        if not user.avatar_url and avatar_url:
            user.avatar_url = avatar_url
        if not user.display_name and display_name:
            user.display_name = display_name
        user.is_verified = True
        user.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_last_login(self, user: User) -> None:
        """Set last_login/updated_at for a user."""
        user.last_login = datetime.now(UTC)
        user.updated_at = datetime.now(UTC)
        self.db.commit()

    def create_session(
        self,
        user_id: uuid.UUID,
        session_token: str,
        expires_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> UserSession:
        """Create a user session record."""
        session = UserSession(
            user_id=user_id,
            session_token=session_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session_by_token(self, token: str) -> UserSession | None:
        """Lookup an active session by token."""
        return (
            self.db.query(UserSession)
            .filter(
                UserSession.session_token == token,
                UserSession.expires_at > datetime.now(UTC),
            )
            .first()
        )

    def revoke_session(self, token: str) -> bool:
        """Revoke a single session by token."""
        session = (
            self.db.query(UserSession)
            .filter(
                UserSession.session_token == token,
            )
            .first()
        )
        if session:
            self.db.delete(session)
            self.db.commit()
            return True
        return False

    def revoke_all_user_sessions(self, user_id: uuid.UUID) -> int:
        """Revoke all sessions for a user and return how many were removed."""
        q = self.db.query(UserSession).filter(UserSession.user_id == user_id)
        count = q.count()
        q.delete()
        self.db.commit()
        return count

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions and return how many were removed."""
        q = self.db.query(UserSession).filter(
            UserSession.expires_at <= datetime.now(UTC),
        )
        count = q.count()
        q.delete()
        self.db.commit()
        return count

    def check_rate_limit(
        self,
        request: Request,
        action: str,
        limit: int,
        window: int = 60,
    ) -> bool:
        """Implement a simple IP-based in-memory rate limiter."""
        # FIXED: Disable rate limiting in test environment or when explicitly disabled
        if TESTING or os.getenv("DISABLE_RATE_LIMIT") == "1":
            return True

        client_ip = request.client.host if request.client else "unknown"
        key = f"{action}:{client_ip}"
        now = datetime.now(UTC).timestamp()

        bucket = _rate_limit_store.setdefault(key, [])
        _rate_limit_store[key] = [t for t in bucket if now - t < window]
        if len(_rate_limit_store[key]) >= limit:
            return False
        _rate_limit_store[key].append(now)
        return True


def _read_secret_from_file(path: str | None) -> str | None:
    p = Path(path) if path else None
    if p and p.exists():
        return p.read_text(encoding="utf-8").strip()
    return None


def get_auth_service(db: Annotated[Session, Depends(get_db)]) -> AuthService:
    """Dependency that returns an AuthService instance."""
    secret_key = os.getenv("SECRET_KEY") or _read_secret_from_file(
        os.getenv("SECRET_KEY_FILE"),
    )
    if not secret_key:
        secret_key = secrets.token_urlsafe(32)
    return AuthService(db, secret_key)


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthenticatedUser | None:
    """Resolve the current authenticated user (token or session cookie)."""
    if credentials and credentials.credentials:
        payload = verify_token(credentials.credentials, auth_service.secret_key)
        if payload:
            user_id_val = payload.get("user_id")
            user = (
                auth_service.get_user_by_id(user_id_val)
                if isinstance(user_id_val, str)
                else None
            )
            if user and user.is_active:
                return AuthenticatedUser(
                    id=str(user.id),
                    username=user.username,
                    email=user.email,
                    display_name=user.display_name,
                    avatar_url=user.avatar_url,
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    permissions=[],
                )

    session_token = request.cookies.get("session_token")
    if session_token:
        session = auth_service.get_session_by_token(session_token)
        if session:
            user = auth_service.get_user_by_id(str(session.user_id))
            if user and user.is_active:
                session.last_activity = datetime.now(UTC)
                auth_service.db.commit()
                return AuthenticatedUser(
                    id=str(user.id),
                    username=user.username,
                    email=user.email,
                    display_name=user.display_name,
                    avatar_url=user.avatar_url,
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    permissions=[],
                )
    return None


def require_authenticated_user(
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user)],
) -> AuthenticatedUser:
    """Dependency that raises if no authenticated user is present."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def require_verified_user(
    current_user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> AuthenticatedUser:
    """Dependency that raises if the authenticated user is not verified."""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    return current_user


def optional_authenticated_user(
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user)],
) -> AuthenticatedUser | None:
    """Return the current user or None."""
    return current_user
