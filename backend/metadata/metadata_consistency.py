from typing import Dict, Any
from backend.database import db, utc_now_iso
from backend.models import ObjectStatus, ReplicaStatus, NodeStatus


class MetadataConsistencyManager:
    """Re-computes and synchronizes object status from its underlying replica states."""

    def refresh_object_status(self, object_id: str) -> Dict[str, Any]:
        obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
        if not obj:
            return {}

        replicas = db.fetch_all(
            """
            SELECT r.*, n.status as node_status
            FROM replicas r
            JOIN nodes n ON r.node_id = n.node_id
            WHERE r.object_id = ?
            """,
            (object_id,),
        )

        healthy_count = sum(
            1
            for r in replicas
            if r["status"] == ReplicaStatus.HEALTHY.value and r["node_status"] == NodeStatus.ONLINE.value
        )
        corrupted_count = sum(1 for r in replicas if r["status"] == ReplicaStatus.CORRUPTED.value)
        repairing_count = sum(1 for r in replicas if r["status"] == ReplicaStatus.REPAIRING.value)

        rf = obj["replication_factor"]
        if healthy_count == 0:
            new_status = ObjectStatus.CORRUPTED.value if corrupted_count > 0 else ObjectStatus.UNAVAILABLE.value
        elif repairing_count > 0:
            new_status = ObjectStatus.REPAIRING.value
        elif healthy_count < rf or corrupted_count > 0:
            new_status = ObjectStatus.DEGRADED.value
        else:
            new_status = ObjectStatus.HEALTHY.value

        now = utc_now_iso()
        with db.transaction() as conn:
            conn.execute(
                "UPDATE objects SET status = ?, updated_at = ? WHERE object_id = ?",
                (new_status, now, object_id),
            )
        return {"object_id": object_id, "status": new_status, "healthy_replicas": healthy_count}


metadata_consistency = MetadataConsistencyManager()
