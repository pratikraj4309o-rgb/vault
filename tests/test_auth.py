import pytest
from fastapi.testclient import TestClient


def test_auth_status_endpoint(client: TestClient):
    resp = client.get("/api/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data
    assert "auth_provider" in data


def test_auth_signup_validation_error(client: TestClient):
    resp = client.post("/api/auth/signup", json={"email": "not-an-email", "password": "123"})
    assert resp.status_code == 422


def test_auth_login_validation_error(client: TestClient):
    resp = client.post("/api/auth/login", json={"email": "not-an-email", "password": "123"})
    assert resp.status_code == 422


def test_auth_get_user_unauthorized(client: TestClient):
    resp = client.get("/api/auth/user")
    assert resp.status_code == 401


def test_auth_logout(client: TestClient):
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_admin_login_and_verify(client: TestClient):
    # Wrong password
    resp = client.post("/api/auth/admin-login", json={"password": "wrong_password"})
    assert resp.status_code == 401

    # Correct password
    from backend.config import settings
    resp = client.post("/api/auth/admin-login", json={"password": settings.admin_password})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["role"] == "admin"
    admin_token = data["admin_token"]

    # Verify with token
    resp_v = client.get("/api/auth/admin-verify", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp_v.status_code == 200
    assert resp_v.json()["is_admin"] is True
