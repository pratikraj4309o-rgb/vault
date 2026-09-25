from typing import List, Dict, Any, Optional
from backend.integrity.corruption import CorruptionSimulator
from backend.integrity.verifier import IntegrityVerifier
from backend.metadata.metadata_manager import metadata_manager
from backend.storage.object_store import object_store

verifier = IntegrityVerifier(object_store=object_store)
corruption_simulator = CorruptionSimulator(object_store=object_store, verifier=verifier)


class ObjectService:
    """High-level service coordinating object queries, verification, and corruption simulation."""

    def list_objects(self) -> List[Dict[str, Any]]:
        return metadata_manager.list_objects_with_replicas()

    def get_object(self, object_id: str) -> Dict[str, Any]:
        return metadata_manager.get_object_with_replicas(object_id)

    def verify_object(self, object_id: str, queue_repair: bool = True) -> Dict[str, Any]:
        return verifier.verify_object(object_id, queue_repair=queue_repair)

    def corrupt_replica(
        self,
        object_id: str,
        node_id: Optional[str] = None,
        replica_id: Optional[str] = None,
        auto_repair: bool = False,
    ) -> Dict[str, Any]:
        return corruption_simulator.corrupt_object_replica(
            object_id=object_id,
            node_id=node_id,
            replica_id=replica_id,
            auto_repair=auto_repair,
        )

    def scan_cluster_integrity(self) -> Dict[str, Any]:
        return verifier.scan_all_objects(queue_repair=True)


object_service = ObjectService()
