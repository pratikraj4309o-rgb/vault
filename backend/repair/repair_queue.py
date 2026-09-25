import uuid
from typing import List, Dict, Any, Optional
from backend.database import db, utc_now_iso
from backend.models import RepairStatus


class RepairQueue:
    """Persistent SQLite-backed repair queue preventing duplicate active repair jobs."""

    def enqueue_repair(
        self,
        object_id: str,
        reason: str,
        failed_node_id: Optional[str] = None,
        source_node_id: Optional[str] = None,
        target_node_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with db.transaction() as conn:
            # Prevent duplicate active repair jobs for the same object and failed node
            existing = conn.execute(
                """
                SELECT * FROM repair_jobs
                WHERE object_id = ?
                  AND COALESCE(failed_node_id, '') = COALESCE(?, '')
                  AND status IN ('QUEUED', 'RUNNING', 'VERIFYING')
                """,
                (object_id, failed_node_id),
            ).fetchone()
            if existing:
                return dict(existing)

            repair_id = f"repjob_{uuid.uuid4().hex[:10]}"
            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO repair_jobs (
                    repair_id, object_id, source_node_id, failed_node_id, target_node_id,
                    reason, status, progress, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repair_id,
                    object_id,
                    source_node_id,
                    failed_node_id,
                    target_node_id,
                    reason,
                    RepairStatus.QUEUED.value,
                    10,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM repair_jobs WHERE repair_id = ?", (repair_id,)
            ).fetchone()
            return dict(row)

    def get_pending_jobs(self) -> List[Dict[str, Any]]:
        return db.fetch_all(
            "SELECT * FROM repair_jobs WHERE status = 'QUEUED' ORDER BY started_at ASC"
        )

    def list_all_jobs(self) -> List[Dict[str, Any]]:
        return db.fetch_all(
            """
            SELECT j.*, o.filename
            FROM repair_jobs j
            LEFT JOIN objects o ON j.object_id = o.object_id
            ORDER BY j.started_at DESC
            """
        )


repair_queue = RepairQueue()
