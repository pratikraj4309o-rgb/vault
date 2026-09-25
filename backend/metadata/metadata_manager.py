from typing import List, Dict, Any, Optional
from backend.database import db
from backend.exceptions import ObjectNotFoundError


class MetadataManager:
    """Provides structured read/write access to object and replica metadata."""

    def get_object_with_replicas(self, object_id: str) -> Dict[str, Any]:
        obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
        if not obj:
            raise ObjectNotFoundError(object_id)

        replicas = db.fetch_all(
            """
            SELECT r.*, n.status as node_status, o.filename, o.checksum as expected_checksum
            FROM replicas r
            JOIN nodes n ON r.node_id = n.node_id
            JOIN objects o ON r.object_id = o.object_id
            WHERE r.object_id = ?
            ORDER BY r.node_id ASC
            """,
            (object_id,),
        )

        healthy_replicas = [
            r for r in replicas if r["status"] == "HEALTHY" and r["node_status"] == "ONLINE"
        ]
        corrupted_replicas = [r for r in replicas if r["status"] == "CORRUPTED"]

        rf = obj["replication_factor"]
        missing = max(0, rf - len(healthy_replicas))
        integrity = "CHECKSUM_MISMATCH" if corrupted_replicas else ("VERIFIED" if len(healthy_replicas) >= rf else "DEGRADED")

        obj["replicas"] = replicas
        obj["current_replicas"] = len(replicas)
        obj["healthy_replicas"] = len(healthy_replicas)
        obj["missing_replicas"] = missing
        obj["integrity"] = integrity
        return obj

    def list_objects_with_replicas(self) -> List[Dict[str, Any]]:
        objects = db.fetch_all("SELECT object_id FROM objects ORDER BY updated_at DESC")
        return [self.get_object_with_replicas(o["object_id"]) for o in objects]

    def find_object_by_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        return db.fetch_one("SELECT * FROM objects WHERE filename = ?", (filename,))


metadata_manager = MetadataManager()
