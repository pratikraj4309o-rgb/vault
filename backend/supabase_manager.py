import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from backend.config import settings
from backend.database import db

logger = logging.getLogger("vault.supabase")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SupabaseManager:
    """Manages cloud metadata synchronization and connectivity with Supabase PostgreSQL."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._client: Optional[Any] = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="supabase_sync")
        self.connected: bool = False
        self.last_error: Optional[str] = None
        self.last_sync_time: Optional[str] = None
        self.last_sync_stats: Dict[str, Any] = {}

        # Auto-connect if environment variables are set
        if settings.supabase_url and settings.supabase_key:
            self._init_client(settings.supabase_url, settings.supabase_key, silent=True)

    def is_configured(self) -> bool:
        return bool(settings.supabase_url and settings.supabase_key)

    def _init_client(self, url: str, key: str, silent: bool = False) -> bool:
        try:
            from supabase import create_client, ClientOptions

            self._client = create_client(url.strip(), key.strip())
            # Quick verification query on schema
            res = self._client.table("vault_nodes").select("node_id").limit(1).execute()
            self.connected = True
            self.last_error = None
            if not silent:
                logger.info("Successfully connected to Supabase project at %s", url)
            return True
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            if not silent:
                logger.warning("Supabase connection check failed: %s", exc)
            return False

    def test_connection(self, url: str, key: str) -> Dict[str, Any]:
        """Test connection against given Supabase credentials without necessarily persisting them."""
        clean_url = (url or "").strip()
        clean_key = (key or "").strip()

        if not clean_url or not clean_key:
            return {
                "success": False,
                "code": "MISSING_CREDENTIALS",
                "message": "Both Supabase Project URL and API Key are required.",
            }

        if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            return {
                "success": False,
                "code": "INVALID_URL",
                "message": "Project URL must begin with https:// or http://",
            }

        try:
            from supabase import create_client

            client = create_client(clean_url, clean_key)

            # Test 1: Check if vault_nodes table exists
            try:
                res = client.table("vault_nodes").select("node_id").limit(1).execute()
                return {
                    "success": True,
                    "code": "OK",
                    "message": "Connection verified! Supabase tables are ready.",
                }
            except Exception as table_err:
                err_str = str(table_err).lower()
                if "relation" in err_str or "does not exist" in err_str or "42p01" in err_str or "pgrst204" in err_str:
                    return {
                        "success": False,
                        "code": "TABLES_MISSING",
                        "message": "Connected to Supabase, but the VAULT tables were not found. Please paste and run the SQL schema in your Supabase SQL Editor.",
                    }
                if "jwt" in err_str or "auth" in err_str or "apikey" in err_str or "unauthorized" in err_str:
                    return {
                        "success": False,
                        "code": "AUTH_FAILED",
                        "message": "Supabase authentication failed. Please verify your Project API Key.",
                    }
                raise table_err
        except Exception as exc:
            return {
                "success": False,
                "code": "CONNECTION_FAILED",
                "message": f"Could not reach Supabase: {str(exc)}",
            }

    def connect(self, url: str, key: str) -> Dict[str, Any]:
        """Test credentials, save to configuration and .env, and trigger an initial sync."""
        with self._lock:
            test_res = self.test_connection(url, key)
            if not test_res["success"]:
                # If tables missing, we still save credentials so user can create tables then click sync
                if test_res.get("code") == "TABLES_MISSING":
                    settings.update_supabase_credentials(url.strip(), key.strip())
                    self._init_client(url.strip(), key.strip(), silent=True)
                    self.connected = False
                    self.last_error = test_res["message"]
                    return {
                        "status": "warning",
                        "message": test_res["message"],
                        "code": "TABLES_MISSING",
                        "configured": True,
                        "connected": False,
                    }
                return {
                    "status": "error",
                    "message": test_res["message"],
                    "code": test_res.get("code", "ERROR"),
                    "configured": False,
                    "connected": False,
                }

            # Save credentials
            settings.update_supabase_credentials(url.strip(), key.strip())
            self._init_client(url.strip(), key.strip(), silent=False)

            # Trigger initial sync of existing data
            sync_res = self.sync_all()

            db.log_activity(
                "SUPABASE_CONNECTED",
                f"Connected to Supabase cloud at {url.strip()}",
                severity="INFO",
                details=f"Initial sync: {sync_res.get('objects_synced', 0)} files, {sync_res.get('nodes_synced', 0)} nodes",
            )

            return {
                "status": "connected",
                "message": "Connected to Supabase and initial cluster sync complete!",
                "configured": True,
                "connected": True,
                "sync": sync_res,
            }

    def disconnect(self) -> Dict[str, Any]:
        with self._lock:
            settings.update_supabase_credentials("", "")
            self._client = None
            self.connected = False
            self.last_error = None
            self.last_sync_stats = {}
            db.log_activity("SUPABASE_DISCONNECTED", "Supabase cloud sync disconnected", severity="INFO")
            return {"status": "disconnected", "message": "Supabase sync disconnected."}

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self.is_configured(),
            "connected": self.connected,
            "url": settings.supabase_url or None,
            "last_sync_time": self.last_sync_time,
            "last_error": self.last_error,
            "stats": self.last_sync_stats,
        }

    def sync_all(self) -> Dict[str, Any]:
        """Reads local SQLite metadata and pushes it to Supabase PostgreSQL."""
        if not self._client:
            return {"status": "skipped", "message": "Supabase client not initialized."}

        try:
            # 1. Sync Nodes
            local_nodes = db.fetch_all("SELECT * FROM nodes")
            nodes_data = []
            for n in local_nodes:
                nodes_data.append({
                    "node_id": n["node_id"],
                    "status": n["status"],
                    "capacity": n["capacity"],
                    "used_capacity": n["used_capacity"],
                    "object_count": n["object_count"],
                    "last_heartbeat": n["last_heartbeat"],
                    "network_status": n["network_status"],
                    "health_status": n["health_status"],
                    "updated_at": utc_now_iso(),
                })
            if nodes_data:
                self._client.table("vault_nodes").upsert(nodes_data).execute()

            # 2. Sync Objects
            local_objects = db.fetch_all("SELECT * FROM objects")
            objects_data = []
            for obj in local_objects:
                objects_data.append({
                    "object_id": obj["object_id"],
                    "filename": obj["filename"],
                    "size": obj["size"],
                    "content_type": obj["content_type"],
                    "checksum": obj["checksum"],
                    "version": obj["version"],
                    "replication_factor": obj["replication_factor"],
                    "status": obj["status"],
                    "created_at": obj["created_at"],
                    "updated_at": obj["updated_at"],
                })
            if objects_data:
                self._client.table("vault_objects").upsert(objects_data).execute()

            # 3. Sync Replicas
            local_replicas = db.fetch_all("SELECT * FROM replicas")
            replicas_data = []
            for rep in local_replicas:
                replicas_data.append({
                    "replica_id": rep["replica_id"],
                    "object_id": rep["object_id"],
                    "node_id": rep["node_id"],
                    "checksum": rep["checksum"],
                    "version": rep["version"],
                    "status": rep["status"],
                    "created_at": rep["created_at"],
                    "updated_at": rep["updated_at"],
                })
            if replicas_data:
                self._client.table("vault_replicas").upsert(replicas_data).execute()

            # 4. Sync Recent Repair Jobs
            local_repairs = db.fetch_all("SELECT * FROM repair_jobs ORDER BY started_at DESC LIMIT 50")
            repairs_data = []
            for r in local_repairs:
                repairs_data.append({
                    "repair_id": r["repair_id"],
                    "object_id": r["object_id"],
                    "source_node_id": r["source_node_id"],
                    "failed_node_id": r["failed_node_id"],
                    "target_node_id": r["target_node_id"],
                    "reason": r["reason"],
                    "status": r["status"],
                    "progress": r["progress"],
                    "started_at": r["started_at"],
                    "completed_at": r["completed_at"],
                    "duration_ms": r["duration_ms"],
                    "error_message": r["error_message"],
                })
            if repairs_data:
                self._client.table("vault_repair_jobs").upsert(repairs_data).execute()

            # 5. Sync Recent Activity Logs
            local_logs = db.fetch_all("SELECT * FROM activity_logs ORDER BY event_id DESC LIMIT 100")
            logs_data = []
            for l in local_logs:
                logs_data.append({
                    "event_type": l["event_type"],
                    "message": l["message"],
                    "object_id": l["object_id"],
                    "node_id": l["node_id"],
                    "severity": l["severity"],
                    "details": l["details"],
                    "created_at": l["created_at"],
                })
            if logs_data:
                # Upsert/insert logs
                self._client.table("vault_activity_logs").insert(logs_data).execute()

            self.connected = True
            self.last_error = None
            self.last_sync_time = utc_now_iso()
            self.last_sync_stats = {
                "nodes": len(nodes_data),
                "objects": len(objects_data),
                "replicas": len(replicas_data),
                "repairs": len(repairs_data),
                "logs": len(logs_data),
                "timestamp": self.last_sync_time,
            }
            logger.info("Supabase sync successful: %s", self.last_sync_stats)
            return {
                "status": "success",
                "nodes_synced": len(nodes_data),
                "objects_synced": len(objects_data),
                "replicas_synced": len(replicas_data),
                "repairs_synced": len(repairs_data),
                "logs_synced": len(logs_data),
                "timestamp": self.last_sync_time,
            }
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            logger.error("Failed to sync metadata to Supabase: %s", exc)
            return {"status": "error", "message": str(exc)}

    def async_sync_node(self, node_id: str) -> None:
        """Asynchronously sync a single node's state."""
        if not self.connected or not self._client:
            return

        def _do_sync():
            try:
                row = db.fetch_one("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
                if row and self._client:
                    data = {
                        "node_id": row["node_id"],
                        "status": row["status"],
                        "capacity": row["capacity"],
                        "used_capacity": row["used_capacity"],
                        "object_count": row["object_count"],
                        "last_heartbeat": row["last_heartbeat"],
                        "network_status": row["network_status"],
                        "health_status": row["health_status"],
                        "updated_at": utc_now_iso(),
                    }
                    self._client.table("vault_nodes").upsert(data).execute()
            except Exception as e:
                logger.debug("Background node sync to Supabase skipped/failed: %s", e)

        self._executor.submit(_do_sync)

    def async_sync_object(self, object_id: str) -> None:
        """Asynchronously sync an object and its replicas."""
        if not self.connected or not self._client:
            return

        def _do_sync():
            try:
                obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
                if obj and self._client:
                    obj_data = {
                        "object_id": obj["object_id"],
                        "filename": obj["filename"],
                        "size": obj["size"],
                        "content_type": obj["content_type"],
                        "checksum": obj["checksum"],
                        "version": obj["version"],
                        "replication_factor": obj["replication_factor"],
                        "status": obj["status"],
                        "created_at": obj["created_at"],
                        "updated_at": obj["updated_at"],
                    }
                    self._client.table("vault_objects").upsert(obj_data).execute()

                    reps = db.fetch_all("SELECT * FROM replicas WHERE object_id = ?", (object_id,))
                    rep_data = [
                        {
                            "replica_id": r["replica_id"],
                            "object_id": r["object_id"],
                            "node_id": r["node_id"],
                            "checksum": r["checksum"],
                            "version": r["version"],
                            "status": r["status"],
                            "created_at": r["created_at"],
                            "updated_at": r["updated_at"],
                        }
                        for r in reps
                    ]
                    if rep_data:
                        self._client.table("vault_replicas").upsert(rep_data).execute()
            except Exception as e:
                logger.debug("Background object sync to Supabase skipped/failed: %s", e)

        self._executor.submit(_do_sync)

    def async_delete_object(self, object_id: str) -> None:
        """Asynchronously delete an object from Supabase."""
        if not self.connected or not self._client:
            return

        def _do_delete():
            try:
                if self._client:
                    self._client.table("vault_objects").delete().eq("object_id", object_id).execute()
            except Exception as e:
                logger.debug("Background object delete from Supabase skipped/failed: %s", e)

        self._executor.submit(_do_delete)

    def async_delete_node(self, node_id: str) -> None:
        """Asynchronously delete a decommissioned node from Supabase."""
        if not self.connected or not self._client:
            return

        def _do_delete():
            try:
                if self._client:
                    self._client.table("vault_nodes").delete().eq("node_id", node_id).execute()
            except Exception as e:
                logger.debug("Background node delete from Supabase skipped/failed: %s", e)

        self._executor.submit(_do_delete)

    # ========================================================
    # SUPABASE AUTHENTICATION
    # ========================================================
    def auth_sign_up(self, email: str, password: str) -> Dict[str, Any]:
        """Registers a new user in Supabase Auth."""
        if not self._client:
            return {"status": "error", "message": "Supabase is not connected. Please connect your project first."}

        try:
            res = self._client.auth.sign_up({"email": email.strip(), "password": password})
            if not res or not res.user:
                return {"status": "error", "message": "Registration failed. No user was returned."}

            user_dict = {
                "id": str(res.user.id),
                "email": res.user.email,
                "created_at": str(res.user.created_at) if res.user.created_at else utc_now_iso(),
            }
            token = res.session.access_token if res.session else None
            needs_confirm = res.session is None and not res.user.email_confirmed_at

            db.log_activity("USER_SIGNUP", f"New user signed up via Supabase Auth: {res.user.email}", severity="INFO")

            return {
                "status": "success",
                "message": "User registered successfully!" if not needs_confirm else "Account created! Please check your email to confirm, or sign in if confirmation is disabled in Supabase.",
                "user": user_dict,
                "access_token": token,
                "requires_confirmation": needs_confirm,
            }
        except Exception as exc:
            err_msg = str(exc)
            if "already registered" in err_msg.lower():
                friendly_msg = "An account with this email already exists. Please click 'Sign In' below to log in."
            elif "rate limit" in err_msg.lower():
                friendly_msg = "Supabase email rate limit reached. In Supabase Dashboard > Authentication > Providers > Email, turn off 'Confirm email'."
            else:
                friendly_msg = err_msg
            logger.warning("Supabase Auth sign up failed: %s", exc)
            return {"status": "error", "message": friendly_msg}

    def auth_sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticates user with email and password via Supabase Auth."""
        if not self._client:
            return {"status": "error", "message": "Supabase is not connected. Please connect your project first."}

        try:
            res = self._client.auth.sign_in_with_password({"email": email.strip(), "password": password})
            if not res or not res.session or not res.user:
                return {"status": "error", "message": "Login failed. Invalid response from Supabase."}

            user_dict = {
                "id": str(res.user.id),
                "email": res.user.email,
                "created_at": str(res.user.created_at) if res.user.created_at else utc_now_iso(),
            }

            db.log_activity("USER_LOGIN", f"User logged in via Supabase Auth: {res.user.email}", severity="INFO")

            return {
                "status": "success",
                "message": f"Welcome back, {res.user.email}!",
                "user": user_dict,
                "access_token": res.session.access_token,
                "token_type": "bearer",
            }
        except Exception as exc:
            err_msg = str(exc)
            if "Email not confirmed" in err_msg:
                friendly_msg = "Email not confirmed yet! Please click the link sent to your email, or in Supabase Dashboard > Authentication > Providers > Email, turn off 'Confirm email'."
            elif "Invalid login credentials" in err_msg:
                friendly_msg = "Invalid email or password. Please check your credentials."
            else:
                friendly_msg = err_msg

            logger.warning("Supabase Auth sign in failed: %s", exc)
            return {"status": "error", "message": friendly_msg}

    def auth_get_user(self, access_token: str) -> Dict[str, Any]:
        """Fetches the current user corresponding to a Supabase JWT."""
        if not self._client or not access_token:
            return {"status": "error", "message": "No active session or Supabase client."}

        try:
            res = self._client.auth.get_user(access_token.strip())
            if res and res.user:
                return {
                    "status": "success",
                    "user": {
                        "id": str(res.user.id),
                        "email": res.user.email,
                        "created_at": str(res.user.created_at) if res.user.created_at else None,
                    },
                }
            return {"status": "error", "message": "Session expired or invalid."}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def auth_sign_out(self, access_token: Optional[str] = None) -> Dict[str, Any]:
        """Signs out the user session."""
        if self._client and access_token:
            try:
                self._client.auth.sign_out(access_token.strip())
            except Exception:
                pass
        return {"status": "success", "message": "Logged out successfully."}

    # ========================================================
    # SUPABASE STORAGE (PHYSICAL OBJECT MIRRORING)
    # ========================================================
    def upload_file_to_storage(
        self,
        object_id: str,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """Mirrors physical file bytes to Supabase Storage bucket 'vault-objects'."""
        if not self.connected or not self._client:
            return False

        try:
            bucket_name = "vault-objects"
            path = f"{object_id}/{filename}"
            self._client.storage.from_(bucket_name).upload(
                path=path,
                file=data,
                file_options={"content-type": content_type, "upsert": "true"},
            )
            logger.info("Successfully mirrored file %s (%s) to Supabase Storage bucket '%s'", object_id, filename, bucket_name)
            return True
        except Exception as exc:
            logger.warning("Could not mirror file to Supabase Storage (run storage policies in schema if bucket is blocked): %s", exc)
            return False

    def delete_file_from_storage(self, object_id: str, filename: Optional[str] = None) -> bool:
        """Removes an object from Supabase Storage bucket."""
        if not self.connected or not self._client:
            return False

        try:
            bucket_name = "vault-objects"
            if filename:
                self._client.storage.from_(bucket_name).remove([f"{object_id}/{filename}"])
            else:
                files = self._client.storage.from_(bucket_name).list(object_id)
                if files:
                    paths = [f"{object_id}/{f['name']}" for f in files]
                    self._client.storage.from_(bucket_name).remove(paths)
            return True
        except Exception as exc:
            logger.warning("Could not delete from Supabase Storage: %s", exc)
            return False

    def async_upload_file(
        self,
        object_id: str,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Asynchronously mirror physical file bytes without blocking local upload."""
        if not self.connected or not self._client:
            return
        self._executor.submit(self.upload_file_to_storage, object_id, filename, data, content_type)

    def async_delete_file_storage(self, object_id: str, filename: Optional[str] = None) -> None:
        """Asynchronously remove object from Supabase Storage."""
        if not self.connected or not self._client:
            return
        self._executor.submit(self.delete_file_from_storage, object_id, filename)


supabase_manager = SupabaseManager()
