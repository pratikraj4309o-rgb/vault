import time
from typing import Dict, Any, List
from backend.config import settings
from backend.database import db, utc_now_iso
from backend.logging_config import logger
from backend.models import EventType
from backend.rebalancing.migration import migrate_replica_safely
from backend.storage.node_manager import node_manager


class Rebalancer:
    """
    Balances replica distribution and storage utilization across healthy storage nodes.
    Supports threshold-triggered rebalancing and explicit user-triggered cluster rebalancing.
    """

    def __init__(self) -> None:
        self._last_run: Dict[str, Any] = {
            "status": "IDLE",
            "objects_moved": 0,
            "bytes_moved": 0,
            "progress": 100,
            "estimated_completion": "0s",
            "movements": [],
            "last_completed_at": None,
        }

    def get_status(self) -> Dict[str, Any]:
        nodes = node_manager.get_all_nodes()
        return {
            **self._last_run,
            "rebalance_threshold": settings.rebalance_threshold,
            "nodes": [
                {
                    "node_id": n["node_id"],
                    "status": n["status"],
                    "used_capacity": n["used_capacity"],
                    "capacity": n["capacity"],
                    "utilization_percent": n["utilization_percent"],
                    "replica_count": n["replica_count"],
                }
                for n in nodes
            ],
        }

    def run_rebalance(self, force_balance: bool = True) -> Dict[str, Any]:
        t0 = time.perf_counter()
        healthy_nodes = node_manager.get_healthy_nodes()
        if len(healthy_nodes) < 2:
            return self.get_status()

        movements: List[Dict[str, Any]] = []
        bytes_moved = 0
        objects_moved = 0

        self._last_run["status"] = "RUNNING"
        self._last_run["progress"] = 25

        with db.transaction() as conn:
            db.log_activity(
                EventType.REBALANCE_STARTED.value,
                "Cluster storage rebalancing started across healthy nodes",
                severity="INFO",
                conn=conn,
            )

        # Iterative balancing: move replicas from most-loaded node to least-loaded node
        max_moves = 10
        for _ in range(max_moves):
            healthy_nodes = node_manager.get_healthy_nodes()
            # Sort descending by (replica_count, used_capacity)
            node_loads = []
            for n in healthy_nodes:
                rep_cnt = db.fetch_one(
                    "SELECT COUNT(*) as cnt FROM replicas WHERE node_id = ? AND status = 'HEALTHY'",
                    (n["node_id"],),
                )["cnt"]
                util = (n["used_capacity"] / max(1, n["capacity"])) * 100.0
                node_loads.append((util, rep_cnt, n["used_capacity"], n["node_id"], n))

            node_loads.sort(key=lambda x: (round(x[0], 2), x[1], x[2], x[3]), reverse=True)
            heaviest = node_loads[0]
            lightest = node_loads[-1]

            heaviest_util, heaviest_cnt, _, source_node_id, _ = heaviest
            lightest_util, lightest_cnt, _, target_node_id, _ = lightest

            if source_node_id == target_node_id:
                break

            # Determine if a move is warranted:
            # Either heaviest exceeds rebalance_threshold, OR (when force_balance=True) replica count/utilization differs
            over_threshold = heaviest_util >= settings.rebalance_threshold
            count_imbalance = (heaviest_cnt - lightest_cnt) > 1
            util_imbalance = (heaviest_util - lightest_util) > 5.0

            if not (over_threshold or (force_balance and (count_imbalance or util_imbalance or heaviest_cnt >= 1))):
                break

            # Find a healthy replica on source_node_id whose object does NOT already have a replica on target_node_id
            candidate_rep = db.fetch_one(
                """
                SELECT r.*, o.filename, o.size, o.checksum as expected_checksum
                FROM replicas r
                JOIN objects o ON r.object_id = o.object_id
                WHERE r.node_id = ?
                  AND r.status = 'HEALTHY'
                  AND r.object_id NOT IN (
                      SELECT object_id FROM replicas WHERE node_id = ? AND status = 'HEALTHY'
                  )
                ORDER BY o.size DESC
                LIMIT 1
                """,
                (source_node_id, target_node_id),
            )

            if not candidate_rep:
                break

            mig = migrate_replica_safely(
                replica_id=candidate_rep["replica_id"],
                object_id=candidate_rep["object_id"],
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                expected_checksum=candidate_rep["expected_checksum"],
                version=candidate_rep["version"],
            )
            mig["filename"] = candidate_rep["filename"]
            mig["size"] = candidate_rep["size"]
            movements.append(mig)
            objects_moved += 1
            bytes_moved += int(candidate_rep["size"])

            # If we only did a demo force-move when counts were equal (e.g. 1 replica per object), one move suffices
            if not over_threshold and not count_imbalance and not util_imbalance:
                break

        duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
        now = utc_now_iso()

        with db.transaction() as conn:
            if movements:
                summary = ", ".join(f"{m['from_node'].upper()} → {m['to_node'].upper()}" for m in movements)
                msg = f"Rebalancing completed ({objects_moved} replica(s) migrated: {summary})"
            else:
                msg = "Rebalancing scan completed — storage distribution is already balanced"
            db.log_activity(
                EventType.REBALANCE_COMPLETED.value,
                msg,
                severity="INFO",
                conn=conn,
            )

        self._last_run = {
            "status": "COMPLETED",
            "objects_moved": objects_moved,
            "bytes_moved": bytes_moved,
            "progress": 100,
            "duration_ms": duration_ms,
            "estimated_completion": "0s (Completed)",
            "movements": movements,
            "last_completed_at": now,
        }
        logger.info("Rebalance completed: %d objects moved (%d bytes) in %dms", objects_moved, bytes_moved, duration_ms)
        return self.get_status()


rebalancer = Rebalancer()
