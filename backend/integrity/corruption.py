import os
from typing import Optional, Dict, Any
from backend.database import db
from backend.exceptions import ObjectNotFoundError, VaultException
from backend.logging_config import logger


class CorruptionSimulator:
    """Simulates bit-rot / disk corruption on a replica file while keeping original metadata checksum."""

    def __init__(self, object_store: Any, verifier: Any) -> None:
        self.object_store = object_store
        self.verifier = verifier

    def corrupt_object_replica(
        self,
        object_id: str,
        node_id: Optional[str] = None,
        replica_id: Optional[str] = None,
        auto_repair: bool = False,
    ) -> Dict[str, Any]:
        obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
        if not obj:
            raise ObjectNotFoundError(object_id)

        if replica_id:
            rep = db.fetch_one(
                "SELECT * FROM replicas WHERE replica_id = ? AND object_id = ?",
                (replica_id, object_id),
            )
        elif node_id:
            rep = db.fetch_one(
                "SELECT * FROM replicas WHERE node_id = ? AND object_id = ?",
                (node_id, object_id),
            )
        else:
            # Pick a healthy replica (preferring non-first replica so node1 remains a clean source)
            reps = db.fetch_all(
                "SELECT * FROM replicas WHERE object_id = ? AND status = 'HEALTHY' ORDER BY node_id DESC",
                (object_id,),
            )
            rep = reps[0] if reps else None

        if not rep:
            raise VaultException(f"No suitable replica found to corrupt for object '{object_id}'", status_code=404)

        target_node = rep["node_id"]
        path = self.object_store.get_replica_path(target_node, object_id)
        if not path.exists():
            raise VaultException(f"Physical replica missing on {target_node} for object {object_id}", status_code=404)

        # Flip bytes / inject bit-rot payload into physical storage file without modifying SQLite expected checksum
        original_bytes = path.read_bytes()
        corrupted_banner = b"__CORRUPTED_BITROT__" + os.urandom(8)
        if len(original_bytes) > len(corrupted_banner):
            tampered = corrupted_banner + original_bytes[len(corrupted_banner) :]
        else:
            tampered = original_bytes + corrupted_banner
        path.write_bytes(tampered)

        logger.warning("Simulated data corruption injected on node %s for object %s", target_node, object_id)

        # Immediately run integrity verification to detect mismatch and queue repair job
        verification_report = self.verifier.verify_object(object_id, queue_repair=True)

        if auto_repair:
            from backend.repair.repair_manager import repair_manager
            repair_manager.process_pending_repairs()

        return {
            "status": "CORRUPTED",
            "object_id": object_id,
            "filename": obj["filename"],
            "corrupted_node_id": target_node,
            "corrupted_replica_id": rep["replica_id"],
            "verification": verification_report,
        }
