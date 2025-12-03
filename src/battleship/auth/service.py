"""Core authentication business logic (Pure Python)."""

from __future__ import annotations

import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from decouple import config

from src.battleship.core.result import ServiceResult
from src.battleship.core.security import (
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from src.battleship.users import models as user_models

if TYPE_CHECKING:
    from uuid import UUID

try:
    from email_validator import validate_email
except ImportError:
    validate_email = None

logger = logging.getLogger(__name__)


def validate_email_format(email_str: str) -> ServiceResult[str]:
    """Validate email format and return normalized email."""
    e = email_str.strip().lower()

    is_strict = not (
        config("EMAIL_SYNTAX_ONLY", default=False, cast=bool)
        or config("TESTING", default=False, cast=bool)
    )

    if not is_strict:
        if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", e):
            return ServiceResult.ok(e)
        return ServiceResult.fail("Invalid email format")

    if not validate_email:
        return ServiceResult.fail("Validation library missing")

    try:
        v = validate_email(e, check_deliverability=False)
        return ServiceResult.ok(cast(str, v.email))
    except Exception:
        return ServiceResult.fail("Invalid email format")


class AuthServiceLogic:
    """Encapsulates Auth logic to keep Routers clean."""

    def __init__(self, auth_service: user_models.AuthService) -> None:
        self.db_service = auth_service

    def process_login(self, email: str, password: str) -> ServiceResult[user_models.User]:
        """Process login and return user on success."""
        email_result = validate_email_format(email)
        if not email_result.success:
            return ServiceResult.fail(email_result.error)

        valid_email = email_result.data
        user = self.db_service.get_user_by_email(valid_email)

        if not user or not user.is_active or not user.password_hash:
            return ServiceResult.fail("Invalid email or password.")

        if not verify_password(password, user.password_hash):
            return ServiceResult.fail("Invalid email or password.")

        return ServiceResult.ok(user)

    def process_registration(
        self, email: str, password: str, confirm: str
    ) -> ServiceResult[user_models.User]:
        """Process registration and return new user on success."""
        email_result = validate_email_format(email)
        if not email_result.success:
            return ServiceResult.fail(email_result.error)

        if password != confirm:
            return ServiceResult.fail("Passwords do not match.")

        is_strong, errors = validate_password_strength(password)
        if not is_strong:
            return ServiceResult.fail(" ".join(errors))

        if self.db_service.get_user_by_email(email_result.data):
            return ServiceResult.fail("Email already registered.")

        password_hash = hash_password(password)
        user = self.db_service.create_user(email_result.data, password_hash)

        return ServiceResult.ok(user)

    def generate_session_data(
        self,
        user: user_models.User,
        remember: bool,
        user_agent: str | None,
        ip: str | None,
    ) -> dict:
        """Generate tokens and persist session to DB."""
        token_data = {"user_id": str(user.id), "email": user.email}
        access_token = create_access_token(token_data, self.db_service.secret_key)

        session_token = secrets.token_urlsafe(32)
        session_duration = timedelta(days=30) if remember else timedelta(hours=24)
        expires_at = datetime.now(UTC) + session_duration

        self.db_service.create_session(
            user_id=cast("UUID", user.id),
            session_token=session_token,
            expires_at=expires_at,
            ip_address=ip,
            user_agent=user_agent,
        )

        return {
            "session_token": session_token,
            "access_token": access_token,
            "max_age": int(session_duration.total_seconds()),
            "secure": config("ENVIRONMENT", default="development") == "production",
        }
