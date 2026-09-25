from typing import Tuple, Dict, Any
from backend.concurrency.locks import lock_manager
from backend.concurrency.request_manager import request_manager
from backend.database import db, utc_now_iso
from backend.exceptions import ObjectNotFoundError, StorageUnavailableError
from backend.integrity.checksum import compute_sha256_file
from backend.logging_config import logger
from backend.metadata.metadata_consistency import metadata_consistency
from backend.models import ReplicaStatus, EventType
from backend.repair.repair_manager import repair_manager
from backend.storage.object_store import object_store


class DownloadService:
    """
    Retrieves object data from healthy replicas with on-the-fly SHA-256 verification.
    Never returns corrupted data if a healthy replica exists, and automatically queues repair
    for any corrupted replica encountered during read.
    """

    def retrieve_object(self, object_id: str) -> Tuple[Dict[str, Any], str, bytes]:
        request_manager.begin_read()
        try:
            with lock_manager.acquire_read(object_id):
                obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
                if not obj:
                    raise ObjectNotFoundError(object_id)

                expected_checksum = obj["checksum"]
                candidates = db.fetch_all(
                    """
                    SELECT r.*, n.status as node_status, n.network_status
                    FROM replicas r
                    JOIN nodes n ON r.node_id = n.node_id
                    WHERE r.object_id = ?
                      AND n.status = 'ONLINE'
                      AND n.network_status = 'CONNECTED'
                    ORDER BY
                      CASE WHEN r.status = 'HEALTHY' THEN 0 ELSE 1 END ASC,
                      r.version DESC,
                      r.node_id ASC
                    """,
                    (object_id,),
                )

                if not candidates:
                    raise StorageUnavailableError(object_id, "No online connected nodes hold a replica")

                corrupted_detected = False
                now = utc_now_iso()

                for rep in candidates:
                    node_id = rep["node_id"]
                    path = object_store.get_replica_path(node_id, object_id)
                    if not path.exists():
                        with db.transaction() as conn:
                            conn.execute(
                                "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                                (ReplicaStatus.MISSING.value, now, rep["replica_id"]),
                            )
                        corrupted_detected = True
                        continue

                    actual_checksum = compute_sha256_file(path)
                    if actual_checksum == expected_checksum and rep["version"] == obj["version"]:
                        data = object_store.read_replica_bytes(node_id, object_id)
                        with db.transaction() as conn:
                            db.log_activity(
                                EventType.OBJECT_DOWNLOADED.value,
                                f"Object downloaded: {obj['filename']} from {node_id.upper()} (SHA-256 verified)",
                                object_id=object_id,
                                node_id=node_id,
                                severity="INFO",
                                conn=conn,
                            )
                        if corrupted_detected:
                            metadata_consistency.refresh_object_status(object_id)
                            repair_manager.evaluate_and_schedule_object_repairs(
                                object_id, reason="Corruption detected during read failover"
                            )
                        return obj, node_id, data
                    else:
                        # Checksum mismatch or stale version detected during read -> mark CORRUPTED and try next replica
                        logger.warning(
                            "Read-time checksum mismatch on %s for %s (expected %s, got %s); failing over",
                            node_id,
                            object_id,
                            expected_checksum,
                            actual_checksum,
                        )
                        with db.transaction() as conn:
                            conn.execute(
                                "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                                (ReplicaStatus.CORRUPTED.value, now, rep["replica_id"]),
                            )
                            db.log_activity(
                                EventType.CORRUPTION_DETECTED.value,
                                f"Read-time SHA-256 mismatch on {node_id.upper()} for {obj['filename']} — failing over to healthy replica",
                                object_id=object_id,
                                node_id=node_id,
                                severity="ERROR",
                                conn=conn,
                            )
                        corrupted_detected = True

                if corrupted_detected:
                    metadata_consistency.refresh_object_status(object_id)
                    repair_manager.evaluate_and_schedule_object_repairs(object_id)

                raise StorageUnavailableError(
                    object_id, "All available replicas failed SHA-256 integrity verification"
                )
        finally:
            request_manager.end_read()


download_service = DownloadService()
