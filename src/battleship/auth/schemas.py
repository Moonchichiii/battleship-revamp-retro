"""Pydantic schemas for authentication and token APIs."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

# Request payloads

class LoginRequest(BaseModel):
    """JSON payload for login."""

    email: EmailStr
    password: str = Field(min_length=1)
    remember: bool = False


class RegisterRequest(BaseModel):
    """JSON payload for registration."""

    email: EmailStr
    password: str = Field(min_length=1)
    confirm_password: str = Field(min_length=1)


# Response models

class UserInfo(BaseModel):
    """Public info about the currently authenticated user."""

    id: str
    username: str
    email: EmailStr
    display_name: str | None = None
    avatar_url: str | None = None
    is_verified: bool


class TokenResponse(BaseModel):
    """Bearer token response."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int = 1800
