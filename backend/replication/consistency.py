from typing import Dict, Any, List, Optional
from backend.database import db, utc_now_iso
from backend.integrity.checksum import compute_sha256_file
from backend.logging_config import logger
from backend.metadata.metadata_consistency import metadata_consistency
from backend.models import ReplicaStatus, EventType
from backend.storage.object_store import object_store


class ConsistencyManager:
    """
    Manages replica version consistency, authoritative replica selection,
    and reconciliation when nodes recover or reconnect from network partitions.
    """

    def select_authoritative_replica(self, object_id: str) -> Optional[Dict[str, Any]]:
        """
        Selects the authoritative healthy replica for an object using highest verified version
        and matching SHA-256 checksum. Never selects stale or corrupted replicas.
        """
        obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
        if not obj:
            return None

        candidates = db.fetch_all(
            """
            SELECT r.*, n.status as node_status
            FROM replicas r
            JOIN nodes n ON r.node_id = n.node_id
            WHERE r.object_id = ? AND n.status = 'ONLINE' AND n.network_status = 'CONNECTED'
            ORDER BY r.version DESC, r.node_id ASC
            """,
            (object_id,),
        )

        for rep in candidates:
            path = object_store.get_replica_path(rep["node_id"], object_id)
            if not path.exists():
                continue
            actual_sha = compute_sha256_file(path)
            if actual_sha == obj["checksum"] and rep["version"] == obj["version"]:
                return rep

        return None

    def check_object_consistency(self, object_id: str) -> Dict[str, Any]:
        """
        Compares all replicas of an object against the authoritative version and checksum.
        Identifies STALE (lower version) or CORRUPTED (checksum mismatch) replicas.
        """
        obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
        if not obj:
            return {"consistent": False, "reason": "Object not found"}

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

        stale_replicas = []
        corrupted_replicas = []
        healthy_replicas = []
        now = utc_now_iso()

        for rep in replicas:
            if rep["node_status"] != "ONLINE":
                continue
            path = object_store.get_replica_path(rep["node_id"], object_id)
            if not path.exists():
                continue
            actual_sha = compute_sha256_file(path)
            if rep["version"] < obj["version"]:
                stale_replicas.append(rep["node_id"])
                with db.transaction() as conn:
                    conn.execute(
                        "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                        (ReplicaStatus.STALE.value, now, rep["replica_id"]),
                    )
            elif actual_sha != obj["checksum"]:
                corrupted_replicas.append(rep["node_id"])
                with db.transaction() as conn:
                    conn.execute(
                        "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                        (ReplicaStatus.CORRUPTED.value, now, rep["replica_id"]),
                    )
            else:
                healthy_replicas.append(rep["node_id"])
                if rep["status"] != ReplicaStatus.HEALTHY.value:
                    with db.transaction() as conn:
                        conn.execute(
                            "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                            (ReplicaStatus.HEALTHY.value, now, rep["replica_id"]),
                        )

        metadata_consistency.refresh_object_status(object_id)

        return {
            "object_id": object_id,
            "authoritative_version": obj["version"],
            "authoritative_checksum": obj["checksum"],
            "consistent": len(stale_replicas) == 0 and len(corrupted_replicas) == 0,
            "healthy_replicas": healthy_replicas,
            "stale_replicas": stale_replicas,
            "corrupted_replicas": corrupted_replicas,
        }

    def reconcile_node_replicas(self, node_id: str) -> Dict[str, Any]:
        """
        Runs when a node recovers or reconnects from a network partition:
        1. Compares replica versions and SHA-256 checksums against authoritative object metadata.
        2. If the object already has full replication (e.g., repaired onto another node during failure),
           removes surplus stale/missing replica on this node to maintain controlled storage overhead.
        3. If the replica is needed and STALE or CORRUPTED, syncs from authoritative replica.
        4. If the replica is needed and matches SHA-256 & version, marks it HEALTHY.
        """
        replicas = db.fetch_all("SELECT * FROM replicas WHERE node_id = ?", (node_id,))
        reconciled_objects: List[Dict[str, Any]] = []
        now = utc_now_iso()

        for rep in replicas:
            obj_id = rep["object_id"]
            obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (obj_id,))
            if not obj:
                object_store.delete_replica(node_id, obj_id)
                continue

            other_healthy = db.fetch_one(
                """
                SELECT COUNT(*) as cnt FROM replicas r
                JOIN nodes n ON r.node_id = n.node_id
                WHERE r.object_id = ? AND r.node_id != ? AND r.status = 'HEALTHY' AND n.status = 'ONLINE'
                """,
                (obj_id, node_id),
            )["cnt"]

            rf = obj["replication_factor"]
            path = object_store.get_replica_path(node_id, obj_id)

            if other_healthy >= rf:
                # Object was already repaired onto a replacement node; clean up surplus replica
                object_store.delete_replica(node_id, obj_id)
                with db.transaction() as conn:
                    conn.execute("DELETE FROM replicas WHERE replica_id = ?", (rep["replica_id"],))
                    db.log_activity(
                        EventType.REPLICA_DELETED.value,
                        f"Pruned redundant replica of {obj['filename']} on recovered {node_id.upper()} (RF={rf} already satisfied)",
                        object_id=obj_id,
                        node_id=node_id,
                        severity="INFO",
                        conn=conn,
                    )
                metadata_consistency.refresh_object_status(obj_id)
                reconciled_objects.append({"object_id": obj_id, "action": "PRUNED_SURPLUS"})
                continue

            # Replica on this node is needed to satisfy RF
            is_stale = rep["version"] < obj["version"]
            actual_sha = compute_sha256_file(path) if path.exists() else None
            is_valid = (not is_stale) and (actual_sha == obj["checksum"])

            if is_valid:
                with db.transaction() as conn:
                    conn.execute(
                        "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                        (ReplicaStatus.HEALTHY.value, now, rep["replica_id"]),
                    )
                    db.log_activity(
                        EventType.CHECKSUM_VERIFIED.value,
                        f"Reconciled replica on {node_id.upper()} for {obj['filename']} (v{obj['version']} SHA-256 verified)",
                        object_id=obj_id,
                        node_id=node_id,
                        severity="INFO",
                        conn=conn,
                    )
                metadata_consistency.refresh_object_status(obj_id)
                reconciled_objects.append({"object_id": obj_id, "action": "VERIFIED_HEALTHY"})
            else:
                # Stale or corrupted replica detected -> sync from authoritative source
                auth = self.select_authoritative_replica(obj_id)
                if auth:
                    new_sha = object_store.copy_replica_between_nodes(auth["node_id"], node_id, obj_id)
                    if new_sha == obj["checksum"]:
                        with db.transaction() as conn:
                            conn.execute(
                                """
                                UPDATE replicas
                                SET status = ?, version = ?, checksum = ?, updated_at = ?
                                WHERE replica_id = ?
                                """,
                                (ReplicaStatus.HEALTHY.value, obj["version"], new_sha, now, rep["replica_id"]),
                            )
                            db.log_activity(
                                EventType.REPAIR_COMPLETED.value,
                                f"Synchronized stale/inconsistent replica on {node_id.upper()} from {auth['node_id'].upper()} (v{rep['version']} → v{obj['version']})",
                                object_id=obj_id,
                                node_id=node_id,
                                severity="INFO",
                                conn=conn,
                            )
                        metadata_consistency.refresh_object_status(obj_id)
                        reconciled_objects.append(
                            {
                                "object_id": obj_id,
                                "action": "RESYNCED_FROM_AUTHORITATIVE",
                                "source_node": auth["node_id"],
                            }
                        )
                else:
                    logger.warning("No authoritative replica available to reconcile %s on %s", obj_id, node_id)

        return {"node_id": node_id, "reconciled": reconciled_objects}


consistency_manager = ConsistencyManager()
