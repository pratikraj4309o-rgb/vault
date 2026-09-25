from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from backend.config import BASE_DIR
from backend.supabase_manager import supabase_manager

router = APIRouter(prefix="/api/supabase", tags=["Supabase Cloud"])


class SupabaseCredentialsRequest(BaseModel):
    supabase_url: str = Field(..., description="Supabase Project URL, e.g. https://xyz.supabase.co")
    supabase_key: str = Field(..., description="Supabase Anon/Public API Key or Service Role Key")


@router.get("/status")
async def get_supabase_status():
    """Returns current Supabase connection status, synced metrics, and error state."""
    return supabase_manager.get_status()


@router.post("/test")
async def test_supabase_connection(payload: SupabaseCredentialsRequest):
    """Verifies connection to a Supabase project and checks if tables exist."""
    res = supabase_manager.test_connection(payload.supabase_url, payload.supabase_key)
    return res


@router.post("/connect")
async def connect_supabase(payload: SupabaseCredentialsRequest):
    """Saves Supabase credentials, tests connection, and runs initial cluster sync."""
    res = supabase_manager.connect(payload.supabase_url, payload.supabase_key)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res)
    return res


@router.post("/sync")
async def trigger_supabase_sync():
    """Manually push all local SQLite metadata (nodes, objects, replicas, activity) to Supabase."""
    if not supabase_manager.connected:
        raise HTTPException(
            status_code=400,
            detail="Supabase is not connected. Please connect with valid credentials first.",
        )
    res = supabase_manager.sync_all()
    if res.get("status") == "error":
        raise HTTPException(status_code=500, detail=res.get("message", "Sync failed"))
    return res


@router.post("/disconnect")
async def disconnect_supabase():
    """Disconnects Supabase cloud sync and clears credentials."""
    return supabase_manager.disconnect()


@router.get("/schema")
async def get_supabase_schema():
    """Returns the SQL schema file contents so users can copy it directly into Supabase SQL editor."""
    schema_path = BASE_DIR / "docs" / "supabase_schema.sql"
    if not schema_path.exists():
        raise HTTPException(status_code=404, detail="Schema file not found")
    sql_text = schema_path.read_text(encoding="utf-8")
    return {
        "filename": "supabase_schema.sql",
        "sql": sql_text,
        "instructions": [
            "1. Open your Supabase Dashboard at https://supabase.com/dashboard",
            "2. Select your project and navigate to 'SQL Editor' in the left menu",
            "3. Paste this SQL script into a new query tab and click 'Run'",
            "4. Return here, paste your Project URL and API Key, and click 'Test & Connect'",
        ],
    }
