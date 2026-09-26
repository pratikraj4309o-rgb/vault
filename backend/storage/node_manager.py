import json
from typing import List, Dict, Any, Optional
from backend.config import settings
from backend.database import db, utc_now_iso
from backend.exceptions import NodeNotFoundError
from backend.logging_config import logger
from backend.models import NodeStatus, ReplicaStatus, ObjectStatus, EventType
from backend.storage.object_store import object_store
from backend.supabase_manager import supabase_manager


class NodeManager:
    """Manages lifecycle, state transitions, heartbeats, and physical directories for storage nodes."""

    def initialize_nodes(self) -> None:
        now = utc_now_iso()
        with db.transaction() as conn:
            for i in range(1, settings.node_count + 1):
                node_id = f"node{i}"
                node_dir = object_store.get_node_dir(node_id)
                node_dir.mkdir(parents=True, exist_ok=True)
                data_dir = object_store.get_node_data_dir(node_id)
                data_dir.mkdir(parents=True, exist_ok=True)
                node_json_path = node_dir / "node.json"

                if not node_json_path.exists():
                    node_meta = {
                        "node_id": node_id,
                        "region": f"us-east-1{chr(96 + i)}",
                        "rack": f"rack-0{i}",
                        "status": NodeStatus.ONLINE.value,
                        "capacity": settings.max_storage_per_node,
                    }
                    node_json_path.write_text(json.dumps(node_meta, indent=2), encoding="utf-8")

                existing = conn.execute(
                    "SELECT node_id FROM nodes WHERE node_id = ?", (node_id,)
                ).fetchone()
                if not existing:
                    conn.execute(
                        """
                        INSERT INTO nodes (
                            node_id, status, capacity, used_capacity,
                            object_count, last_heartbeat, network_status, health_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            node_id,
                            NodeStatus.ONLINE.value,
                            settings.max_storage_per_node,
                            0,
                            0,
                            now,
                            "CONNECTED",
                            "HEALTHY",
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE nodes
                        SET status = ?, capacity = ?, last_heartbeat = ?, network_status = 'CONNECTED', health_status = 'HEALTHY'
                        WHERE node_id = ?
                        """,
                        (NodeStatus.ONLINE.value, settings.max_storage_per_node, now, node_id),
                    )
        self.refresh_all_node_metrics()
        logger.info("Initialized %d simulated storage nodes", settings.node_count)

    def refresh_node_metrics(self, node_id: str, conn: Optional[Any] = None) -> None:
        data_dir = object_store.get_node_data_dir(node_id)
        files = [f for f in data_dir.iterdir() if f.is_file() and not f.name.endswith(".tmp") and not f.name.startswith(".")]
        physical_bytes = sum(f.stat().st_size for f in files)

        def _update(c: Any) -> None:
            row = c.execute(
                """
                SELECT COUNT(*) as cnt, COALESCE(SUM(o.size), 0) as logical_bytes
                FROM replicas r
                JOIN objects o ON r.object_id = o.object_id
                WHERE r.node_id = ? AND r.status IN ('HEALTHY', 'CORRUPTED', 'STALE', 'REPAIRING')
                """,
                (node_id,),
            ).fetchone()
            obj_count = row["cnt"] if row else len(files)
            used_cap = max(physical_bytes, row["logical_bytes"] if row else 0)
            c.execute(
                "UPDATE nodes SET used_capacity = ?, object_count = ? WHERE node_id = ?",
                (used_cap, obj_count, node_id),
            )

        if conn is not None:
            _update(conn)
        else:
            with db.transaction() as c:
                _update(c)

    def refresh_all_node_metrics(self) -> None:
        nodes = db.fetch_all("SELECT node_id FROM nodes ORDER BY node_id ASC")
        with db.transaction() as conn:
            for n in nodes:
                self.refresh_node_metrics(n["node_id"], conn=conn)

    def get_all_nodes(self) -> List[Dict[str, Any]]:
        self.prune_repaired_failed_nodes()
        self.refresh_all_node_metrics()
        nodes = db.fetch_all("SELECT * FROM nodes ORDER BY node_id ASC")
        result = []
        for n in nodes:
            cap = max(1, n["capacity"])
            util = round((n["used_capacity"] / cap) * 100.0, 2)
            rep_row = db.fetch_one(
                "SELECT COUNT(*) as cnt FROM replicas WHERE node_id = ?", (n["node_id"],)
            )
            n["utilization_percent"] = min(100.0, util)
            n["replica_count"] = rep_row["cnt"] if rep_row else 0
            result.append(n)
        return result

    def get_node(self, node_id: str) -> Dict[str, Any]:
        self.refresh_node_metrics(node_id)
        node = db.fetch_one("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        if not node:
            raise NodeNotFoundError(node_id)
        cap = max(1, node["capacity"])
        node["utilization_percent"] = min(100.0, round((node["used_capacity"] / cap) * 100.0, 2))
        replicas = db.fetch_all(
            """
            SELECT r.*, o.filename, o.size, o.checksum as expected_checksum
            FROM replicas r
            JOIN objects o ON r.object_id = o.object_id
            WHERE r.node_id = ?
            ORDER BY r.created_at DESC
            """,
            (node_id,),
        )
        node["replica_count"] = len(replicas)
        node["replicas"] = replicas
        return node

    def get_healthy_nodes(self) -> List[Dict[str, Any]]:
        self.refresh_all_node_metrics()
        nodes = db.fetch_all(
            "SELECT * FROM nodes WHERE status = 'ONLINE' AND network_status = 'CONNECTED' ORDER BY node_id ASC"
        )
        if not nodes:
            self.initialize_nodes()
            nodes = db.fetch_all(
                "SELECT * FROM nodes WHERE status = 'ONLINE' AND network_status = 'CONNECTED' ORDER BY node_id ASC"
            )
        return nodes

    def get_next_node_id(self) -> str:
        max_num = settings.node_count
        rows = db.fetch_all("SELECT node_id FROM nodes")
        for r in rows:
            nid = r["node_id"]
            if nid.startswith("node") and nid[4:].isdigit():
                max_num = max(max_num, int(nid[4:]))
        if object_store._storage_root and object_store._storage_root.exists():
            try:
                for p in object_store._storage_root.iterdir():
                    if p.is_dir() and p.name.startswith("node") and p.name[4:].isdigit():
                        max_num = max(max_num, int(p.name[4:]))
            except Exception:
                pass
        return f"node{max_num + 1}"

    def provision_node(
        self,
        node_id: Optional[str] = None,
        reason: str = "Dynamic cluster auto-scaling",
    ) -> Dict[str, Any]:
        """Dynamically provisions a new storage node (e.g., node6, node7) with physical directories and metadata."""
        new_node_id = node_id or self.get_next_node_id()
        existing = db.fetch_one("SELECT * FROM nodes WHERE node_id = ?", (new_node_id,))
        if existing:
            return self.get_node(new_node_id)

        now = utc_now_iso()
        node_dir = object_store.get_node_dir(new_node_id)
        object_store.get_node_data_dir(new_node_id)
        node_num = int(new_node_id[4:]) if new_node_id.startswith("node") and new_node_id[4:].isdigit() else 6
        node_meta = {
            "node_id": new_node_id,
            "region": f"us-autoscale-{node_num}",
            "rack": f"rack-{node_num:02d}",
            "status": NodeStatus.ONLINE.value,
            "capacity": settings.max_storage_per_node,
            "auto_scaled": True,
            "reason": reason,
        }
        (node_dir / "node.json").write_text(json.dumps(node_meta, indent=2), encoding="utf-8")

        with db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO nodes (
                    node_id, status, capacity, used_capacity,
                    object_count, last_heartbeat, network_status, health_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_node_id,
                    NodeStatus.ONLINE.value,
                    settings.max_storage_per_node,
                    0,
                    0,
                    now,
                    "CONNECTED",
                    "HEALTHY",
                ),
            )
            db.log_activity(
                EventType.AUTO_SCALED.value,
                f"Auto-scaled cluster: provisioned new storage node {new_node_id.upper()} ({reason})",
                node_id=new_node_id,
                severity="INFO",
                conn=conn,
            )

        logger.info("Auto-scaled new storage node %s (%s)", new_node_id, reason)
        supabase_manager.async_sync_node(new_node_id)
        return self.get_node(new_node_id)

    def ensure_minimum_healthy_nodes(
        self,
        min_required: int,
        reason: str = "Maintaining cluster replication factor",
    ) -> List[Dict[str, Any]]:
        """Ensures at least `min_required` healthy nodes are online, dynamically spawning new nodes if auto-scale is enabled."""
        provisioned: List[Dict[str, Any]] = []
        if not settings.auto_scale_enabled:
            return provisioned

        total_nodes = len(db.fetch_all("SELECT node_id FROM nodes"))
        healthy = self.get_healthy_nodes()
        while len(healthy) < min_required and total_nodes < settings.max_auto_scale_nodes:
            new_node = self.provision_node(reason=reason)
            provisioned.append(new_node)
            total_nodes += 1
            healthy = self.get_healthy_nodes()
        return provisioned

    def decommission_node(self, node_id: str) -> Dict[str, Any]:
        """Safely drains any replicas from a dynamically scaled node and removes it from the cluster."""
        node = db.fetch_one("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        if not node:
            raise NodeNotFoundError(node_id)

        # Migrate any healthy replicas off this node before removal
        replicas = db.fetch_all("SELECT * FROM replicas WHERE node_id = ?", (node_id,))
        for r in replicas:
            object_store.delete_replica(node_id, r["object_id"])

        with db.transaction() as conn:
            conn.execute("DELETE FROM replicas WHERE node_id = ?", (node_id,))
            conn.execute("DELETE FROM nodes WHERE node_id = ?", (node_id,))
            db.log_activity(
                EventType.AUTO_SCALED.value,
                f"Decommissioned storage node {node_id.upper()} from cluster",
                node_id=node_id,
                severity="INFO",
                conn=conn,
            )
        supabase_manager.async_delete_node(node_id)
        return {"decommissioned": True, "node_id": node_id}

    def prune_repaired_failed_nodes(self) -> List[str]:
        """Checks all FAILED nodes. If all affected objects have been fully repaired and RF is satisfied,
        safely decommissions the dead node and removes it from the cluster and Supabase."""
        failed_nodes = db.fetch_all("SELECT node_id FROM nodes WHERE status = 'FAILED'")
        pruned: List[str] = []
        for fn in failed_nodes:
            nid = fn["node_id"]
            # 1. Check if there are active repair jobs involving this failed node
            active_jobs = db.fetch_one(
                """
                SELECT COUNT(*) as cnt FROM repair_jobs
                WHERE failed_node_id = ? AND status IN ('QUEUED', 'RUNNING', 'VERIFYING')
                """,
                (nid,),
            )
            if active_jobs and active_jobs["cnt"] > 0:
                continue

            # 2. Check if any object still has a MISSING replica on this node that lacks RF healthy replicas
            unresolved = db.fetch_one(
                """
                SELECT COUNT(*) as cnt FROM replicas r
                JOIN objects o ON r.object_id = o.object_id
                WHERE r.node_id = ? AND r.status = 'MISSING'
                AND (
                    SELECT COUNT(*) FROM replicas r2
                    JOIN nodes n2 ON r2.node_id = n2.node_id
                    WHERE r2.object_id = o.object_id AND r2.status = 'HEALTHY' AND n2.status = 'ONLINE'
                ) < o.replication_factor
                """,
                (nid,),
            )
            if unresolved and unresolved["cnt"] > 0:
                continue

            # 3. Only prune if repairs were completed or node had no objects
            unhealthy_objs = db.fetch_one(
                """
                SELECT COUNT(*) as cnt FROM objects o
                JOIN replicas r ON o.object_id = r.object_id
                WHERE r.node_id = ? AND o.status != 'HEALTHY'
                """,
                (nid,),
            )
            if unhealthy_objs and unhealthy_objs["cnt"] > 0:
                continue

            reps_on_node = db.fetch_all("SELECT * FROM replicas WHERE node_id = ?", (nid,))
            if reps_on_node:
                rep_count = db.fetch_one(
                    """
                    SELECT COUNT(*) as cnt FROM repair_jobs
                    WHERE failed_node_id = ? AND status = 'COMPLETED'
                    """,
                    (nid,),
                )
                if not rep_count or rep_count["cnt"] == 0:
                    continue

            self.decommission_node(nid)
            pruned.append(nid)
            logger.info("Automatically pruned and decommissioned repaired crashed storage node %s", nid)

        return pruned

    def fail_node(
        self,
        node_id: str,
        auto_repair: bool = True,
        force_autoscale: bool = False,
    ) -> Dict[str, Any]:
        node = db.fetch_one("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        if not node:
            raise NodeNotFoundError(node_id)

        now = utc_now_iso()
        affected_objects: List[str] = []

        with db.transaction() as conn:
            conn.execute(
                """
                UPDATE nodes
                SET status = ?, network_status = 'DISCONNECTED', health_status = 'CRITICAL', last_heartbeat = ?
                WHERE node_id = ?
                """,
                (NodeStatus.FAILED.value, now, node_id),
            )
            reps = conn.execute(
                "SELECT replica_id, object_id FROM replicas WHERE node_id = ?", (node_id,)
            ).fetchall()
            for r in reps:
                conn.execute(
                    "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                    (ReplicaStatus.MISSING.value, now, r["replica_id"]),
                )
                if r["object_id"] not in affected_objects:
                    affected_objects.append(r["object_id"])

            for obj_id in affected_objects:
                healthy_cnt = conn.execute(
                    """
                    SELECT COUNT(*) as cnt FROM replicas r
                    JOIN nodes n ON r.node_id = n.node_id
                    WHERE r.object_id = ? AND r.status = 'HEALTHY' AND n.status = 'ONLINE'
                    """,
                    (obj_id,),
                ).fetchone()["cnt"]
                new_obj_status = (
                    ObjectStatus.DEGRADED.value if healthy_cnt > 0 else ObjectStatus.UNAVAILABLE.value
                )
                conn.execute(
                    "UPDATE objects SET status = ?, updated_at = ? WHERE object_id = ?",
                    (new_obj_status, now, obj_id),
                )

            db.log_activity(
                EventType.NODE_FAILED.value,
                f"Storage node {node_id.upper()} marked FAILED — {len(affected_objects)} object(s) degraded",
                node_id=node_id,
                severity="ERROR",
                conn=conn,
            )

        logger.warning("Node %s failed; %d objects affected", node_id, len(affected_objects))

        auto_scaled_nodes: List[Dict[str, Any]] = []
        if auto_repair and settings.auto_scale_enabled:
            healthy_count = len(self.get_healthy_nodes())
            if force_autoscale or healthy_count < settings.node_count or healthy_count < settings.replication_factor:
                spawned = self.provision_node(
                    reason=f"Auto-scaling replacement node for crashed {node_id.upper()}"
                )
                auto_scaled_nodes.append(spawned)
            else:
                spawned_list = self.ensure_minimum_healthy_nodes(
                    min_required=settings.replication_factor,
                    reason=f"Node {node_id.upper()} failed; scaling to maintain RF={settings.replication_factor}",
                )
                auto_scaled_nodes.extend(spawned_list)

        from backend.repair.repair_manager import repair_manager
        created_jobs = []
        target_override = auto_scaled_nodes[0]["node_id"] if auto_scaled_nodes else None
        for obj_id in affected_objects:
            jobs = repair_manager.evaluate_and_schedule_object_repairs(
                obj_id,
                failed_node_id=node_id,
                target_node_id=target_override,
                reason=f"Node {node_id} failure" + (f" (Auto-scaled → {target_override.upper()})" if target_override else ""),
            )
            created_jobs.extend(jobs)

        if auto_repair and created_jobs:
            repair_manager.process_pending_repairs()
            self.prune_repaired_failed_nodes()

        supabase_manager.async_sync_node(node_id)
        for an in auto_scaled_nodes:
            supabase_manager.async_sync_node(an["node_id"])

        node_exists = db.fetch_one("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        node_ret = self.get_node(node_id) if node_exists else {"node_id": node_id, "status": NodeStatus.FAILED.value, "pruned": True}

        return {
            "node": node_ret,
            "affected_objects": affected_objects,
            "auto_scaled_nodes": auto_scaled_nodes,
            "scheduled_repairs": created_jobs,
        }

    def restore_node(self, node_id: str) -> Dict[str, Any]:
        node = db.fetch_one("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        if not node:
            raise NodeNotFoundError(node_id)

        now = utc_now_iso()
        with db.transaction() as conn:
            conn.execute(
                """
                UPDATE nodes
                SET status = ?, network_status = 'CONNECTED', health_status = 'HEALTHY', last_heartbeat = ?
                WHERE node_id = ?
                """,
                (NodeStatus.ONLINE.value, now, node_id),
            )
            db.log_activity(
                EventType.NODE_RECOVERED.value,
                f"Storage node {node_id.upper()} restored to ONLINE state and reconciled",
                node_id=node_id,
                severity="INFO",
                conn=conn,
            )

        # Reconcile replicas stored on this recovered node
        from backend.replication.consistency import consistency_manager
        reconciled = consistency_manager.reconcile_node_replicas(node_id)
        self.refresh_node_metrics(node_id)

        supabase_manager.async_sync_node(node_id)

        return {
            "node": self.get_node(node_id),
            "reconciliation": reconciled,
        }

    def partition_node(self, node_id: str) -> Dict[str, Any]:
        """Simulates temporary network partition: node is PARTITIONED (unreachable), not permanently destroyed."""
        node = db.fetch_one("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        if not node:
            raise NodeNotFoundError(node_id)

        now = utc_now_iso()
        affected_objects: List[str] = []
        with db.transaction() as conn:
            conn.execute(
                """
                UPDATE nodes
                SET status = ?, network_status = 'PARTITIONED', health_status = 'WARNING'
                WHERE node_id = ?
                """,
                (NodeStatus.PARTITIONED.value, node_id),
            )
            reps = conn.execute(
                "SELECT replica_id, object_id FROM replicas WHERE node_id = ?", (node_id,)
            ).fetchall()
            for r in reps:
                conn.execute(
                    "UPDATE replicas SET status = ?, updated_at = ? WHERE replica_id = ?",
                    (ReplicaStatus.UNAVAILABLE.value, now, r["replica_id"]),
                )
                if r["object_id"] not in affected_objects:
                    affected_objects.append(r["object_id"])

            for obj_id in affected_objects:
                obj_row = conn.execute(
                    "SELECT replication_factor FROM objects WHERE object_id = ?", (obj_id,)
                ).fetchone()
                rf = obj_row["replication_factor"] if obj_row else settings.replication_factor
                healthy_cnt = conn.execute(
                    """
                    SELECT COUNT(*) as cnt FROM replicas r
                    JOIN nodes n ON r.node_id = n.node_id
                    WHERE r.object_id = ? AND r.status = 'HEALTHY' AND n.status = 'ONLINE'
                    """,
                    (obj_id,),
                ).fetchone()["cnt"]
                new_status = (
                    ObjectStatus.HEALTHY.value
                    if healthy_cnt >= rf
                    else (ObjectStatus.DEGRADED.value if healthy_cnt > 0 else ObjectStatus.UNAVAILABLE.value)
                )
                conn.execute(
                    "UPDATE objects SET status = ?, updated_at = ? WHERE object_id = ?",
                    (new_status, now, obj_id),
                )

            db.log_activity(
                EventType.NETWORK_PARTITION.value,
                f"Network partition simulated on {node_id.upper()} (TEMPORARILY UNREACHABLE — metadata preserved)",
                node_id=node_id,
                severity="WARNING",
                conn=conn,
            )

        return {
            "node": self.get_node(node_id),
            "affected_objects": affected_objects,
        }

    def reconnect_node(self, node_id: str) -> Dict[str, Any]:
        """Reconnects a partitioned node, compares replica versions & checksums, detects stale replicas, and repairs."""
        node = db.fetch_one("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        if not node:
            raise NodeNotFoundError(node_id)

        now = utc_now_iso()
        with db.transaction() as conn:
            conn.execute(
                """
                UPDATE nodes
                SET status = ?, network_status = 'CONNECTED', health_status = 'HEALTHY', last_heartbeat = ?
                WHERE node_id = ?
                """,
                (NodeStatus.ONLINE.value, now, node_id),
            )
            db.log_activity(
                EventType.NETWORK_RECONNECTED.value,
                f"Node {node_id.upper()} reconnected after network partition — initiating version & checksum reconciliation",
                node_id=node_id,
                severity="INFO",
                conn=conn,
            )

        from backend.replication.consistency import consistency_manager
        reconciliation = consistency_manager.reconcile_node_replicas(node_id)
        self.refresh_node_metrics(node_id)

        return {
            "node": self.get_node(node_id),
            "reconciliation": reconciliation,
        }


node_manager = NodeManager()
