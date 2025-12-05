"""Argon2 password hashing & JWT utilities."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, status
from jose import JWTError, jwt

# Initialize the Argon2 Hasher (Default parameters are secure)
_HASHER = PasswordHasher()

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

DEFAULT_TOKEN_TYPE = "access"


def hash_password(plaintext: str) -> str:
    """Hash password using Argon2."""
    return _HASHER.hash(plaintext)


def verify_password(plaintext: str, password_hash: str) -> bool:
    """Return True if plaintext matches hash; False on any verification error."""
    try:
        # verify() returns True or raises VerifyMismatchError
        _HASHER.verify(password_hash, plaintext)
        return True
    except (VerifyMismatchError, ValueError, TypeError):
        # VerifyMismatchError: Wrong password
        # ValueError/TypeError: Invalid hash format or malformed string
        return False


def validate_password_strength(password: str) -> tuple[bool, list[str]]:
    """Validate password strength."""
    errors: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        errors.append(f"Password must be no more than {MAX_PASSWORD_LENGTH} characters")
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit")
    return len(errors) == 0, errors


def create_access_token(
    data: dict[str, Any],
    secret_key: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {
        **data,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "jti": secrets.token_urlsafe(16),
        "token_type": DEFAULT_TOKEN_TYPE,
    }
    return jwt.encode(to_encode, secret_key, algorithm=JWT_ALGORITHM)


def verify_token(
    token: str,
    secret_key: str,
    *,
    expected_type: str = DEFAULT_TOKEN_TYPE,
) -> dict[str, Any] | None:
    """Verify and decode a JWT; return payload or None."""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("token_type") != expected_type:
        return None
    return payload


class SecurityUtils:
    """Misc. security helpers."""

    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate a random URL-safe token."""
        return secrets.token_urlsafe(length)

    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, list[str]]:
        """Proxy to validator (back-compat)."""
        return validate_password_strength(password)


class AuthenticationError(HTTPException):
    """Auth error with WWW-Authenticate header."""

    def __init__(self, detail: str = "Authentication failed") -> None:
        """Initialize an AuthenticationError returning 401 with a WWW-Authenticate header."""
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
