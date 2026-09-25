import uuid
from typing import Dict, Any
from backend.database import db, utc_now_iso
from backend.exceptions import VaultException
from backend.models import ReplicaStatus
from backend.storage.node_manager import node_manager
from backend.storage.object_store import object_store


def migrate_replica_safely(
    replica_id: str,
    object_id: str,
    source_node_id: str,
    target_node_id: str,
    expected_checksum: str,
    version: int,
) -> Dict[str, Any]:
    """
    Migrates a replica from source_node_id to target_node_id:
    1. Copies physical data to target_node_id
    2. Verifies SHA-256 checksum on target_node_id
    3. Updates metadata to point replica to target_node_id
    4. Deletes source replica ONLY AFTER destination replica is verified
    """
    actual_checksum = object_store.copy_replica_between_nodes(
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        object_id=object_id,
    )
    if actual_checksum != expected_checksum:
        object_store.delete_replica(target_node_id, object_id)
        raise VaultException(
            f"Rebalance migration verification failed on {target_node_id}: expected {expected_checksum}, got {actual_checksum}"
        )

    now = utc_now_iso()
    with db.transaction() as conn:
        conn.execute(
            """
            UPDATE replicas
            SET node_id = ?, checksum = ?, version = ?, status = ?, updated_at = ?
            WHERE replica_id = ?
            """,
            (target_node_id, actual_checksum, version, ReplicaStatus.HEALTHY.value, now, replica_id),
        )

    # Only delete source replica AFTER destination is verified and metadata committed
    object_store.delete_replica(source_node_id, object_id)
    node_manager.refresh_node_metrics(source_node_id)
    node_manager.refresh_node_metrics(target_node_id)

    return {
        "migration_id": f"mig_{uuid.uuid4().hex[:8]}",
        "replica_id": replica_id,
        "object_id": object_id,
        "from_node": source_node_id,
        "to_node": target_node_id,
        "checksum_verified": True,
        "completed_at": now,
    }
