import os
import re
import uuid
from typing import Optional, Dict, Any
from backend.concurrency.locks import lock_manager
from backend.concurrency.request_manager import request_manager
from backend.concurrency.versioning import validate_expected_version
from backend.config import settings
from backend.database import db, utc_now_iso
from backend.exceptions import InvalidConfigurationError
from backend.integrity.checksum import compute_sha256_bytes
from backend.logging_config import logger
from backend.metadata.metadata_manager import metadata_manager
from backend.models import ObjectStatus, EventType
from backend.replication.placement_policy import validate_and_select_nodes
from backend.replication.replica_manager import replica_manager
from backend.supabase_manager import supabase_manager


def sanitize_filename(filename: str) -> str:
    if not filename:
        raise InvalidConfigurationError("Filename cannot be empty")
    base = os.path.basename(filename.replace("\\", "/")).strip()
    base = re.sub(r"[^a-zA-Z0-9_\-\.\s\(\)]", "_", base)
    if not base or base in (".", ".."):
        raise InvalidConfigurationError(f"Unsafe filename: '{filename}'")
    return base


class UploadService:
    """Implements the 12-step fault-tolerant upload and replication workflow."""

    def upload_object(
        self,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        replication_factor: Optional[int] = None,
        object_id: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        safe_name = sanitize_filename(filename)
        rf = replication_factor if replication_factor is not None else settings.replication_factor

        lock_key = object_id or f"file:{safe_name}"
        request_manager.begin_write()
        try:
            with lock_manager.acquire_write(lock_key):
                existing = None
                if object_id:
                    existing = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
                elif expected_version is not None:
                    existing = metadata_manager.find_object_by_filename(safe_name)

                if existing:
                    obj_id = existing["object_id"]
                    new_version = validate_expected_version(existing["version"], expected_version)
                    created_at = existing["created_at"]
                else:
                    if expected_version is not None and expected_version > 1:
                        validate_expected_version(0, expected_version)
                    obj_id = object_id or f"obj_{uuid.uuid4().hex[:12]}"
                    new_version = 1
                    created_at = utc_now_iso()

                now = utc_now_iso()
                size = len(data)
                checksum = compute_sha256_bytes(data)

                # Select healthy nodes using placement policy
                if existing:
                    # Prefer updating existing online replica nodes first if count matches
                    existing_reps = db.fetch_all(
                        """
                        SELECT n.* FROM replicas r
                        JOIN nodes n ON r.node_id = n.node_id
                        WHERE r.object_id = ? AND n.status = 'ONLINE' AND n.network_status = 'CONNECTED'
                        ORDER BY n.node_id ASC
                        """,
                        (obj_id,),
                    )
                    if len(existing_reps) >= rf:
                        selected_nodes = existing_reps[:rf]
                    else:
                        selected_nodes = validate_and_select_nodes(replication_factor=rf, object_size=size)
                else:
                    selected_nodes = validate_and_select_nodes(replication_factor=rf, object_size=size)

                # Insert or update object metadata BEFORE replica foreign-key insertion
                with db.transaction() as conn:
                    if existing:
                        conn.execute(
                            """
                            UPDATE objects
                            SET filename = ?, size = ?, content_type = ?, checksum = ?,
                                version = ?, updated_at = ?, replication_factor = ?, status = ?
                            WHERE object_id = ?
                            """,
                            (
                                safe_name,
                                size,
                                content_type,
                                checksum,
                                new_version,
                                now,
                                rf,
                                ObjectStatus.HEALTHY.value,
                                obj_id,
                            ),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO objects (
                                object_id, filename, size, content_type, checksum,
                                version, created_at, updated_at, replication_factor, status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                obj_id,
                                safe_name,
                                size,
                                content_type,
                                checksum,
                                new_version,
                                created_at,
                                now,
                                rf,
                                ObjectStatus.HEALTHY.value,
                            ),
                        )

                # Store and verify replicas on each selected node
                replica_manager.store_and_verify_replicas(
                    object_id=obj_id,
                    filename=safe_name,
                    data=data,
                    expected_checksum=checksum,
                    version=new_version,
                    target_nodes=selected_nodes,
                )

                node_list_str = ", ".join(n["node_id"].upper() for n in selected_nodes)
                with db.transaction() as conn:
                    db.log_activity(
                        EventType.OBJECT_UPLOADED.value,
                        f"Object uploaded: {safe_name} (v{new_version}, {size} B, RF={rf}) → [{node_list_str}]",
                        object_id=obj_id,
                        severity="INFO",
                        conn=conn,
                    )
                    db.log_activity(
                        EventType.CHECKSUM_VERIFIED.value,
                        f"All {rf} replica(s) verified with SHA-256 {checksum[:12]}...",
                        object_id=obj_id,
                        severity="INFO",
                        conn=conn,
                    )

                logger.info(
                    "Uploaded object %s (%s) v%d size=%d to nodes %s",
                    obj_id,
                    safe_name,
                    new_version,
                    size,
                    node_list_str,
                )

                # Sync metadata & mirror physical file bytes to Supabase in background
                supabase_manager.async_sync_object(obj_id)
                supabase_manager.async_upload_file(obj_id, safe_name, data, content_type)
                for n in selected_nodes:
                    supabase_manager.async_sync_node(n["node_id"])

                return metadata_manager.get_object_with_replicas(obj_id)
        finally:
            request_manager.end_write()


upload_service = UploadService()
