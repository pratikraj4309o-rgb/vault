from typing import Dict, Any, List
from backend.database import db, utc_now_iso
from backend.exceptions import ObjectNotFoundError
from backend.integrity.checksum import compute_sha256_file
from backend.logging_config import logger
from backend.models import ReplicaStatus, ObjectStatus, EventType, NodeStatus


class IntegrityVerifier:
    """Verifies SHA-256 checksums of physical replicas against metadata records."""

    def __init__(self, object_store: Any) -> None:
        self.object_store = object_store

    def verify_object(self, object_id: str, queue_repair: bool = True) -> Dict[str, Any]:
        obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
        if not obj:
            raise ObjectNotFoundError(object_id)

        expected_checksum = obj["checksum"]
        replicas = db.fetch_all(
            """
            SELECT r.*, n.status as node_status
            FROM replicas r
            JOIN nodes n ON r.node_id = n.node_id
            WHERE r.object_id = ?
            ORDER BY r.node_id ASC
            """,
            (object_id,),
        )

        results: List[Dict[str, Any]] = []
        healthy_count = 0
        corrupted_count = 0
        missing_count = 0
        now = utc_now_iso()

        for rep in replicas:
            node_id = rep["node_id"]
            replica_id = rep["replica_id"]
            node_status = rep["node_status"]

            if node_status in (NodeStatus.FAILED.value, NodeStatus.OFFLINE.value, NodeStatus.PARTITIONED.value):
                new_status = (
                    ReplicaStatus.UNAVAILABLE.value
                    if node_status == NodeStatus.PARTITIONED.value
                    else ReplicaStatus.MISSING.value
                )
                with db.transaction() as conn:
                    conn.execute(
                        "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                        (new_status, now, replica_id),
                    )
                missing_count += 1
                results.append(
                    {
                        "replica_id": replica_id,
                        "object_id": object_id,
                        "filename": obj["filename"],
                        "node_id": node_id,
                        "expected_checksum": expected_checksum,
                        "actual_checksum": None,
                        "status": new_status,
                        "verified": False,
                        "reason": f"Node {node_id} is {node_status}",
                    }
                )
                continue

            path = self.object_store.get_replica_path(node_id, object_id)
            if not path.exists():
                with db.transaction() as conn:
                    conn.execute(
                        "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                        (ReplicaStatus.MISSING.value, now, replica_id),
                    )
                missing_count += 1
                results.append(
                    {
                        "replica_id": replica_id,
                        "object_id": object_id,
                        "filename": obj["filename"],
                        "node_id": node_id,
                        "expected_checksum": expected_checksum,
                        "actual_checksum": None,
                        "status": ReplicaStatus.MISSING.value,
                        "verified": False,
                        "reason": "Physical replica file missing on disk",
                    }
                )
                continue

            actual_checksum = compute_sha256_file(path)
            if actual_checksum == expected_checksum and rep["version"] == obj["version"]:
                with db.transaction() as conn:
                    conn.execute(
                        "UPDATE replicas SET status = ?, checksum = ?, updated_at = ? WHERE replica_id = ?",
                        (ReplicaStatus.HEALTHY.value, actual_checksum, now, replica_id),
                    )
                healthy_count += 1
                results.append(
                    {
                        "replica_id": replica_id,
                        "object_id": object_id,
                        "filename": obj["filename"],
                        "node_id": node_id,
                        "expected_checksum": expected_checksum,
                        "actual_checksum": actual_checksum,
                        "status": "VERIFIED",
                        "verified": True,
                    }
                )
            elif rep["version"] < obj["version"]:
                with db.transaction() as conn:
                    conn.execute(
                        "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                        (ReplicaStatus.STALE.value, now, replica_id),
                    )
                missing_count += 1
                results.append(
                    {
                        "replica_id": replica_id,
                        "object_id": object_id,
                        "filename": obj["filename"],
                        "node_id": node_id,
                        "expected_checksum": expected_checksum,
                        "actual_checksum": actual_checksum,
                        "status": ReplicaStatus.STALE.value,
                        "verified": False,
                        "reason": f"Stale version {rep['version']} < {obj['version']}",
                    }
                )
            else:
                with db.transaction() as conn:
                    conn.execute(
                        "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                        (ReplicaStatus.CORRUPTED.value, now, replica_id),
                    )
                    db.log_activity(
                        EventType.CORRUPTION_DETECTED.value,
                        f"SHA-256 mismatch detected for {obj['filename']} on {node_id} (expected {expected_checksum[:12]}..., got {actual_checksum[:12]}...)",
                        object_id=object_id,
                        node_id=node_id,
                        severity="ERROR",
                        conn=conn,
                    )
                corrupted_count += 1
                logger.warning(
                    "Corruption detected on %s for object %s: expected=%s actual=%s",
                    node_id,
                    object_id,
                    expected_checksum,
                    actual_checksum,
                )
                results.append(
                    {
                        "replica_id": replica_id,
                        "object_id": object_id,
                        "filename": obj["filename"],
                        "node_id": node_id,
                        "expected_checksum": expected_checksum,
                        "actual_checksum": actual_checksum,
                        "status": "CHECKSUM_MISMATCH",
                        "verified": False,
                    }
                )

        rf = obj["replication_factor"]
        if healthy_count == 0:
            obj_status = ObjectStatus.CORRUPTED.value if corrupted_count > 0 else ObjectStatus.UNAVAILABLE.value
        elif corrupted_count > 0 or healthy_count < rf:
            obj_status = ObjectStatus.DEGRADED.value
        else:
            obj_status = ObjectStatus.HEALTHY.value

        with db.transaction() as conn:
            conn.execute(
                "UPDATE objects SET status = ?, updated_at = ? WHERE object_id = ?",
                (obj_status, now, object_id),
            )
            if corrupted_count == 0 and healthy_count >= rf:
                db.log_activity(
                    EventType.CHECKSUM_VERIFIED.value,
                    f"Integrity verified for {obj['filename']} ({healthy_count}/{rf} replicas match SHA-256 {expected_checksum[:12]}...)",
                    object_id=object_id,
                    severity="INFO",
                    conn=conn,
                )

        if queue_repair and (corrupted_count > 0 or healthy_count < rf):
            from backend.repair.repair_manager import repair_manager
            repair_manager.evaluate_and_schedule_object_repairs(object_id)

        return {
            "object_id": object_id,
            "filename": obj["filename"],
            "expected_checksum": expected_checksum,
            "object_status": obj_status,
            "integrity": "VERIFIED" if (corrupted_count == 0 and healthy_count >= rf) else "CHECKSUM_MISMATCH",
            "healthy_replicas": healthy_count,
            "corrupted_replicas": corrupted_count,
            "missing_replicas": max(0, rf - healthy_count),
            "replicas": results,
        }

    def scan_all_objects(self, queue_repair: bool = True) -> Dict[str, Any]:
        objects = db.fetch_all("SELECT object_id FROM objects ORDER BY created_at DESC")
        reports = []
        total_corrupted = 0
        total_healthy_objects = 0
        for row in objects:
            res = self.verify_object(row["object_id"], queue_repair=queue_repair)
            reports.append(res)
            total_corrupted += res["corrupted_replicas"]
            if res["object_status"] == ObjectStatus.HEALTHY.value:
                total_healthy_objects += 1

        return {
            "scanned_objects": len(reports),
            "healthy_objects": total_healthy_objects,
            "corrupted_replicas_detected": total_corrupted,
            "reports": reports,
        }
