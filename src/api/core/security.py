"""Argon2 password hashing & verification utilities."""

from __future__ import annotations

from typing import Final

from passlib.context import CryptContext

# Single, shared Passlib context (Argon2 only)
_PWD_CONTEXT: Final[CryptContext] = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
)


def hash_password(plaintext: str) -> str:
    """Return a secure Argon2 hash for the given plaintext password."""
    return _PWD_CONTEXT.hash(plaintext)


def verify_password(plaintext: str, password_hash: str) -> bool:
    """Return True if plaintext matches the given Argon2 password hash."""
    return _PWD_CONTEXT.verify(plaintext, password_hash)
