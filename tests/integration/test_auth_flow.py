"""Comprehensive authentication tests aligned with current routes."""

from __future__ import annotations

import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from main import app

from src.battleship.core.database import SessionLocal
from src.battleship.users.models import AuthService

HTTP_OK = 200
HTTP_SEE_OTHER = 303
TEST_SECRET_KEY = "test-secret-key"

@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)

@pytest.fixture()
def db_session() -> Generator:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture()
def auth_service(db_session) -> AuthService:
    return AuthService(db_session, TEST_SECRET_KEY)

class TestUserRegistration:
    def test_successful_registration(self, client: TestClient) -> None:
        data = {
            "email": "test-reg@example.com",
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
        }
        # HTMX Response expected
        resp = client.post("/auth/register", data=data, headers={"HX-Request": "true"})
        assert resp.status_code == HTTP_OK
        assert "Account created" in resp.text

class TestUserLogin:
    def test_successful_login(self, client: TestClient) -> None:
        # Pre-register
        reg_data = {
            "email": "test-login@example.com",
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
        }
        client.post("/auth/register", data=reg_data)
        
        # Login
        resp = client.post(
            "/auth/login",
            data={"email": "test-login@example.com", "password": "SecurePass123!"},
            follow_redirects=False,
        )
        # Should redirect if not HTMX
        assert resp.status_code == HTTP_SEE_OTHER
        assert "session_token" in client.cookies