import time
import uuid
from typing import List, Dict, Any, Optional
from backend.database import db, utc_now_iso
from backend.exceptions import RepairJobNotFoundError
from backend.logging_config import logger
from backend.metadata.metadata_consistency import metadata_consistency
from backend.models import RepairStatus, ReplicaStatus, ObjectStatus, EventType
from backend.repair.repair_queue import repair_queue
from backend.replication.consistency import consistency_manager
from backend.storage.node_manager import node_manager
from backend.storage.object_store import object_store
from backend.storage.placement import placement_engine


class RepairManager:
    """
    Coordinates detection of degraded/corrupted replicas and executes self-healing repairs:
    1. Detect missing or corrupted replica
    2. Create repair job
    3. Select healthy authoritative source replica
    4. Select healthy destination node (in-place if target node is ONLINE, or replacement node if FAILED)
    5. Copy object data
    6. Calculate & compare SHA-256 checksum
    7. Mark replica & object HEALTHY, record repair duration, and emit activity events
    """

    def evaluate_and_schedule_object_repairs(
        self,
        object_id: str,
        failed_node_id: Optional[str] = None,
        target_node_id: Optional[str] = None,
        reason: str = "Automatic integrity/availability repair",
    ) -> List[Dict[str, Any]]:
        obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
        if not obj:
            return []

        replicas = db.fetch_all(
            """
            SELECT r.*, n.status as node_status
            FROM replicas r
            JOIN nodes n ON r.node_id = n.node_id
            WHERE r.object_id = ?
            """,
            (object_id,),
        )

        healthy_online = [
            r for r in replicas if r["status"] == ReplicaStatus.HEALTHY.value and r["node_status"] == "ONLINE"
        ]
        corrupted_or_stale = [
            r
            for r in replicas
            if r["status"] in (ReplicaStatus.CORRUPTED.value, ReplicaStatus.STALE.value)
            and r["node_status"] == "ONLINE"
        ]
        failed_replicas = [
            r
            for r in replicas
            if r["status"] == ReplicaStatus.MISSING.value or r["node_status"] == "FAILED"
        ]

        created_jobs: List[Dict[str, Any]] = []

        # 1. Schedule repairs for any corrupted or stale replicas on ONLINE nodes (in-place repair)
        for bad_rep in corrupted_or_stale:
            job = repair_queue.enqueue_repair(
                object_id=object_id,
                failed_node_id=bad_rep["node_id"],
                target_node_id=bad_rep["node_id"],
                reason=f"Replica {bad_rep['status']} on {bad_rep['node_id']}",
            )
            created_jobs.append(job)

        # 2. Schedule replacement repairs if effective healthy + repairing replicas < replication_factor
        needed = obj["replication_factor"] - (len(healthy_online) + len(corrupted_or_stale))
        for i in range(max(0, needed)):
            f_node = failed_node_id
            if not f_node and i < len(failed_replicas):
                f_node = failed_replicas[i]["node_id"]
            job = repair_queue.enqueue_repair(
                object_id=object_id,
                failed_node_id=f_node,
                target_node_id=target_node_id if i == 0 else None,
                reason=reason,
            )
            created_jobs.append(job)

        return created_jobs

    def execute_repair_job(self, repair_id: str) -> Dict[str, Any]:
        job = db.fetch_one("SELECT * FROM repair_jobs WHERE repair_id = ?", (repair_id,))
        if not job:
            raise RepairJobNotFoundError(repair_id)

        t0 = time.perf_counter()
        object_id = job["object_id"]
        obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
        if not obj:
            self._fail_job(repair_id, "Object deleted before repair could run")
            return db.fetch_one("SELECT * FROM repair_jobs WHERE repair_id = ?", (repair_id,)) or {}

        # Step 3: Select healthy authoritative source replica
        source_rep = consistency_manager.select_authoritative_replica(object_id)
        if not source_rep:
            self._fail_job(repair_id, "No healthy verified source replica available")
            return db.fetch_one("SELECT * FROM repair_jobs WHERE repair_id = ?", (repair_id,)) or {}

        source_node_id = source_rep["node_id"]
        failed_node_id = job["failed_node_id"]

        # Step 4: Determine target node
        target_node_id = job["target_node_id"]
        if not target_node_id:
            if failed_node_id:
                f_node_row = db.fetch_one("SELECT * FROM nodes WHERE node_id = ?", (failed_node_id,))
                if f_node_row and f_node_row["status"] == "ONLINE" and f_node_row["network_status"] == "CONNECTED":
                    target_node_id = failed_node_id

        if not target_node_id:
            # Find a healthy replacement node that does not already hold a healthy replica of this object
            existing_healthy_nodes = {
                r["node_id"]
                for r in db.fetch_all(
                    """
                    SELECT r.node_id FROM replicas r
                    JOIN nodes n ON r.node_id = n.node_id
                    WHERE r.object_id = ? AND r.status = 'HEALTHY' AND n.status = 'ONLINE'
                    """,
                    (object_id,),
                )
            }
            existing_healthy_nodes.add(source_node_id)
            try:
                selected = placement_engine.select_nodes_for_object(
                    required_count=1,
                    object_size=obj["size"],
                    exclude_node_ids=existing_healthy_nodes,
                )
                target_node_id = selected[0]["node_id"]
            except Exception as exc:
                from backend.config import settings
                if settings.auto_scale_enabled:
                    spawned = node_manager.provision_node(
                        reason=f"Auto-scaling replacement node to repair {obj['filename']}"
                    )
                    target_node_id = spawned["node_id"]
                else:
                    self._fail_job(repair_id, str(exc))
                    return db.fetch_one("SELECT * FROM repair_jobs WHERE repair_id = ?", (repair_id,)) or {}

        now = utc_now_iso()
        with db.transaction() as conn:
            conn.execute(
                """
                UPDATE repair_jobs
                SET source_node_id = ?, target_node_id = ?, status = ?, progress = 50
                WHERE repair_id = ?
                """,
                (source_node_id, target_node_id, RepairStatus.RUNNING.value, repair_id),
            )
            conn.execute(
                "UPDATE objects SET status = ?, updated_at = ? WHERE object_id = ?",
                (ObjectStatus.REPAIRING.value, now, object_id),
            )
            db.log_activity(
                EventType.REPAIR_STARTED.value,
                f"Repair started for {obj['filename']}: copying {source_node_id.upper()} → {target_node_id.upper()}",
                object_id=object_id,
                node_id=target_node_id,
                severity="WARNING",
                conn=conn,
            )

        # Step 5 & 6: Copy object and calculate SHA-256 checksum
        try:
            actual_checksum = object_store.copy_replica_between_nodes(
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                object_id=object_id,
            )
        except Exception as exc:
            self._fail_job(repair_id, f"Copy failed: {exc}")
            return db.fetch_one("SELECT * FROM repair_jobs WHERE repair_id = ?", (repair_id,)) or {}

        with db.transaction() as conn:
            conn.execute(
                "UPDATE repair_jobs SET status = ?, progress = 85 WHERE repair_id = ?",
                (RepairStatus.VERIFYING.value, repair_id),
            )

        # Step 7: Compare SHA-256 checksum
        if actual_checksum != obj["checksum"]:
            object_store.delete_replica(target_node_id, object_id)
            self._fail_job(
                repair_id,
                f"Checksum mismatch after repair copy: expected {obj['checksum']}, got {actual_checksum}",
            )
            return db.fetch_one("SELECT * FROM repair_jobs WHERE repair_id = ?", (repair_id,)) or {}

        # Step 8-12: Update replica & object metadata, record duration, log completion
        duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
        completed_at = utc_now_iso()

        with db.transaction() as conn:
            existing_rep = conn.execute(
                "SELECT replica_id FROM replicas WHERE object_id = ? AND node_id = ?",
                (object_id, target_node_id),
            ).fetchone()

            if existing_rep:
                conn.execute(
                    """
                    UPDATE replicas
                    SET checksum = ?, version = ?, status = ?, updated_at = ?
                    WHERE replica_id = ?
                    """,
                    (
                        actual_checksum,
                        obj["version"],
                        ReplicaStatus.HEALTHY.value,
                        completed_at,
                        existing_rep["replica_id"],
                    ),
                )
            else:
                new_rep_id = f"rep_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO replicas (
                        replica_id, object_id, node_id, checksum, version, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_rep_id,
                        object_id,
                        target_node_id,
                        actual_checksum,
                        obj["version"],
                        ReplicaStatus.HEALTHY.value,
                        completed_at,
                        completed_at,
                    ),
                )

            conn.execute(
                """
                UPDATE repair_jobs
                SET status = ?, progress = 100, completed_at = ?, duration_ms = ?, error_message = NULL
                WHERE repair_id = ?
                """,
                (RepairStatus.COMPLETED.value, completed_at, duration_ms, repair_id),
            )

            db.log_activity(
                EventType.CHECKSUM_VERIFIED.value,
                f"Checksum verified on {target_node_id.upper()} for {obj['filename']} (SHA-256 match)",
                object_id=object_id,
                node_id=target_node_id,
                severity="INFO",
                conn=conn,
            )
            db.log_activity(
                EventType.REPAIR_COMPLETED.value,
                f"Replica restored {source_node_id.upper()} → {target_node_id.upper()} for {obj['filename']} in {duration_ms}ms",
                object_id=object_id,
                node_id=target_node_id,
                severity="INFO",
                conn=conn,
            )

        node_manager.refresh_node_metrics(target_node_id)
        metadata_consistency.refresh_object_status(object_id)
        logger.info(
            "Completed repair %s for object %s (%s -> %s) in %dms",
            repair_id,
            object_id,
            source_node_id,
            target_node_id,
            duration_ms,
        )
        return db.fetch_one("SELECT * FROM repair_jobs WHERE repair_id = ?", (repair_id,)) or {}

    def _fail_job(self, repair_id: str, error_msg: str) -> None:
        now = utc_now_iso()
        job = db.fetch_one("SELECT * FROM repair_jobs WHERE repair_id = ?", (repair_id,))
        with db.transaction() as conn:
            conn.execute(
                """
                UPDATE repair_jobs
                SET status = ?, completed_at = ?, error_message = ?
                WHERE repair_id = ?
                """,
                (RepairStatus.FAILED.value, now, error_msg, repair_id),
            )
            db.log_activity(
                EventType.REPAIR_FAILED.value,
                f"Repair job {repair_id} failed: {error_msg}",
                object_id=job["object_id"] if job else None,
                severity="ERROR",
                conn=conn,
            )
        if job:
            metadata_consistency.refresh_object_status(job["object_id"])

    def process_pending_repairs(self) -> List[Dict[str, Any]]:
        # Also scan for any degraded objects that lack a repair job
        degraded_objs = db.fetch_all(
            "SELECT object_id FROM objects WHERE status IN ('DEGRADED', 'CORRUPTED')"
        )
        for o in degraded_objs:
            self.evaluate_and_schedule_object_repairs(o["object_id"])

        pending = repair_queue.get_pending_jobs()
        completed = []
        for job in pending:
            res = self.execute_repair_job(job["repair_id"])
            completed.append(res)

        if completed:
            node_manager.prune_repaired_failed_nodes()

        return completed

    def retry_repair(self, repair_id: str) -> Dict[str, Any]:
        job = db.fetch_one("SELECT * FROM repair_jobs WHERE repair_id = ?", (repair_id,))
        if not job:
            raise RepairJobNotFoundError(repair_id)
        with db.transaction() as conn:
            conn.execute(
                """
                UPDATE repair_jobs
                SET status = 'QUEUED', progress = 10, error_message = NULL, completed_at = NULL
                WHERE repair_id = ?
                """,
                (repair_id,),
            )
        return self.execute_repair_job(repair_id)


repair_manager = RepairManager()
