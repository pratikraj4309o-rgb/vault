import uuid
from typing import List, Dict, Any
from backend.database import db, utc_now_iso
from backend.exceptions import VaultException
from backend.models import ReplicaStatus, EventType
from backend.storage.node_manager import node_manager
from backend.storage.object_store import object_store


class ReplicaManager:
    """Handles creation, verification, and metadata persistence of object replicas across nodes."""

    def store_and_verify_replicas(
        self,
        object_id: str,
        filename: str,
        data: bytes,
        expected_checksum: str,
        version: int,
        target_nodes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        created_replicas: List[Dict[str, Any]] = []
        now = utc_now_iso()

        for node in target_nodes:
            node_id = node["node_id"]
            actual_checksum = object_store.write_replica_bytes(node_id, object_id, data)
            if actual_checksum != expected_checksum:
                object_store.delete_replica(node_id, object_id)
                raise VaultException(
                    f"Replica verification failed on {node_id}: expected {expected_checksum}, got {actual_checksum}"
                )

            existing = db.fetch_one(
                "SELECT replica_id FROM replicas WHERE object_id = ? AND node_id = ?",
                (object_id, node_id),
            )
            replica_id = existing["replica_id"] if existing else f"rep_{uuid.uuid4().hex[:12]}"

            with db.transaction() as conn:
                if existing:
                    conn.execute(
                        """
                        UPDATE replicas
                        SET checksum = ?, version = ?, status = ?, updated_at = ?
                        WHERE replica_id = ?
                        """,
                        (actual_checksum, version, ReplicaStatus.HEALTHY.value, now, replica_id),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO replicas (
                            replica_id, object_id, node_id, checksum, version, status, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            replica_id,
                            object_id,
                            node_id,
                            actual_checksum,
                            version,
                            ReplicaStatus.HEALTHY.value,
                            now,
                            now,
                        ),
                    )

                db.log_activity(
                    EventType.REPLICA_CREATED.value,
                    f"Replica verified & stored → {node_id.upper()} for {filename} (v{version})",
                    object_id=object_id,
                    node_id=node_id,
                    severity="INFO",
                    conn=conn,
                )

            node_manager.refresh_node_metrics(node_id)
            created_replicas.append(
                {
                    "replica_id": replica_id,
                    "object_id": object_id,
                    "node_id": node_id,
                    "checksum": actual_checksum,
                    "version": version,
                    "status": ReplicaStatus.HEALTHY.value,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        return created_replicas

    def list_all_replicas(self) -> List[Dict[str, Any]]:
        rows = db.fetch_all(
            """
            SELECT r.*, o.filename, o.size, o.checksum as expected_checksum, n.status as node_status
            FROM replicas r
            JOIN objects o ON r.object_id = o.object_id
            JOIN nodes n ON r.node_id = n.node_id
            ORDER BY r.updated_at DESC
            """
        )
        return rows


replica_manager = ReplicaManager()
