import pytest
from fastapi.testclient import TestClient


def test_supabase_status_endpoint(client: TestClient):
    resp = client.get("/api/supabase/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data
    assert "connected" in data


def test_supabase_schema_endpoint(client: TestClient):
    resp = client.get("/api/supabase/schema")
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "supabase_schema.sql"
    assert "CREATE TABLE IF NOT EXISTS vault_nodes" in data["sql"]
    assert len(data["instructions"]) > 0


def test_supabase_test_missing_credentials(client: TestClient):
    resp = client.post("/api/supabase/test", json={"supabase_url": "", "supabase_key": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["code"] == "MISSING_CREDENTIALS"


def test_supabase_connect_invalid_url(client: TestClient):
    resp = client.post("/api/supabase/connect", json={"supabase_url": "invalid_url_without_http", "supabase_key": "some_key"})
    assert resp.status_code == 400
    err = resp.json()["detail"]
    assert err["code"] == "INVALID_URL"


def test_supabase_disconnect(client: TestClient):
    resp = client.post("/api/supabase/disconnect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "disconnected"
