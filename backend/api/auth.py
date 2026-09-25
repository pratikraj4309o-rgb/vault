from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field, EmailStr
from typing import Optional

from backend.supabase_manager import supabase_manager

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class AuthCredentials(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password (min 6 characters)")


@router.get("/status")
async def get_auth_status():
    """Returns current Supabase Auth configuration status."""
    return {
        "configured": supabase_manager.is_configured(),
        "connected": supabase_manager.connected,
        "auth_provider": "Supabase Auth (GoTrue)",
    }


@router.post("/signup")
async def sign_up(payload: AuthCredentials):
    """Registers a new user account in Supabase Auth."""
    res = supabase_manager.auth_sign_up(payload.email, payload.password)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Sign up failed"))
    return res


@router.post("/login")
async def login(payload: AuthCredentials):
    """Authenticates user with email and password via Supabase Auth, or Admin credentials."""
    clean_email = payload.email.lower().strip()

    # Check if administrator credentials (email: admin or admin@... with admin password)
    if payload.password == settings.admin_password and (
        clean_email in ("admin", "admin@vault.local", "admin@admin.com", "admin@gmail.com", "admin@nexstore.com")
        or clean_email.startswith("admin@")
        or clean_email == "admin"
    ):
        token = hashlib.sha256(f"admin-{settings.admin_password}".encode()).hexdigest()
        user_dict = {
            "id": "admin-vault-001",
            "email": "admin@vault.local",
            "role": "admin",
        }
        db.log_activity("ADMIN_LOGIN", f"Administrator logged in via credentials ({payload.email})", severity="INFO")
        return {
            "status": "success",
            "role": "admin",
            "is_admin": True,
            "user": user_dict,
            "access_token": token,
            "admin_token": token,
            "token_type": "bearer",
            "message": "Welcome back, Administrator!",
        }

    # Otherwise authenticate via Supabase Auth
    res = supabase_manager.auth_sign_in(payload.email, payload.password)
    if res.get("status") == "error":
        raise HTTPException(status_code=401, detail=res.get("message", "Invalid login credentials"))
    return res


@router.get("/user")
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Retrieves current user identity from Supabase using Bearer token or Admin session."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split("Bearer ", 1)[1].strip()

    expected_admin = hashlib.sha256(f"admin-{settings.admin_password}".encode()).hexdigest()
    if token == expected_admin:
        return {
            "status": "success",
            "is_admin": True,
            "user": {
                "id": "admin-vault-001",
                "email": "admin@vault.local",
                "role": "admin",
            },
        }

    res = supabase_manager.auth_get_user(token)
    if res.get("status") == "error":
        raise HTTPException(status_code=401, detail=res.get("message", "Session invalid"))
    return res


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Signs out user session."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
    return supabase_manager.auth_sign_out(token)


# ========================================================
# ADMIN PASSWORD & PRIVILEGED CLUSTER ACCESS
# ========================================================
import hashlib
from backend.config import settings
from backend.database import db


class AdminLoginRequest(BaseModel):
    password: str = Field(..., description="Cluster admin password")


class AdminChangePassRequest(BaseModel):
    current_password: str = Field(..., description="Current admin password")
    new_password: str = Field(..., min_length=4, description="New admin password (min 4 chars)")


@router.post("/admin-login")
async def admin_login(payload: AdminLoginRequest):
    """Verifies cluster admin password and grants administrator privileges."""
    if payload.password == settings.admin_password:
        token = hashlib.sha256(f"admin-{settings.admin_password}".encode()).hexdigest()
        db.log_activity("ADMIN_LOGIN", "Administrator unlocked cluster control via Admin Pass", severity="INFO")
        return {
            "status": "success",
            "role": "admin",
            "admin_token": token,
            "message": "Admin privileges granted.",
        }
    raise HTTPException(status_code=401, detail="Invalid admin password.")


@router.post("/admin-change-pass")
async def admin_change_password(payload: AdminChangePassRequest):
    """Changes the cluster administrator password and persists to .env."""
    if payload.current_password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Current admin password incorrect.")
    settings.update_admin_password(payload.new_password)
    db.log_activity("ADMIN_PASS_CHANGED", "Admin password successfully updated", severity="INFO")
    return {"status": "success", "message": "Admin password updated successfully."}


@router.get("/admin-verify")
async def admin_verify(authorization: Optional[str] = Header(None)):
    """Verifies if given admin token or header is valid."""
    expected_token = hashlib.sha256(f"admin-{settings.admin_password}".encode()).hexdigest()
    if authorization and authorization.startswith("Bearer "):
        provided_token = authorization.split("Bearer ", 1)[1].strip()
        if provided_token == expected_token:
            return {"status": "success", "is_admin": True}
    return {"status": "unauthorized", "is_admin": False}
