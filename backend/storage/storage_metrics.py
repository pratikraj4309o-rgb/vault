from typing import Dict, Any
from backend.config import settings
from backend.database import db
from backend.storage.node_manager import node_manager


def get_cluster_metrics() -> Dict[str, Any]:
    nodes = node_manager.get_all_nodes()
    total_nodes = len(nodes)
    active_nodes = sum(1 for n in nodes if n["status"] == "ONLINE")
    failed_nodes = sum(1 for n in nodes if n["status"] == "FAILED")
    partitioned_nodes = sum(1 for n in nodes if n["status"] == "PARTITIONED")

    total_storage = sum(n["capacity"] for n in nodes)
    used_storage = sum(n["used_capacity"] for n in nodes)
    available_storage = max(0, total_storage - used_storage)

    obj_stats = db.fetch_one(
        """
        SELECT
            COUNT(*) as total_objects,
            COALESCE(SUM(size), 0) as logical_storage,
            SUM(CASE WHEN status = 'HEALTHY' THEN 1 ELSE 0 END) as healthy_objects,
            SUM(CASE WHEN status IN ('DEGRADED', 'REPAIRING') THEN 1 ELSE 0 END) as degraded_objects,
            SUM(CASE WHEN status IN ('CORRUPTED', 'UNAVAILABLE') THEN 1 ELSE 0 END) as corrupted_objects
        FROM objects
        """
    ) or {}

    logical_storage = int(obj_stats.get("logical_storage") or 0)

    rep_stats = db.fetch_one(
        """
        SELECT
            COUNT(*) as total_replicas,
            SUM(CASE WHEN r.status = 'HEALTHY' THEN 1 ELSE 0 END) as healthy_replicas,
            SUM(CASE WHEN r.status = 'CORRUPTED' THEN 1 ELSE 0 END) as corrupted_replicas,
            COALESCE(SUM(o.size), 0) as physical_storage
        FROM replicas r
        JOIN objects o ON r.object_id = o.object_id
        WHERE r.status IN ('HEALTHY', 'CORRUPTED', 'STALE', 'REPAIRING')
        """
    ) or {}

    physical_storage = max(used_storage, int(rep_stats.get("physical_storage") or 0))
    storage_overhead = max(0, physical_storage - logical_storage)

    repair_stats = db.fetch_one(
        """
        SELECT
            SUM(CASE WHEN status IN ('QUEUED', 'RUNNING', 'VERIFYING') THEN 1 ELSE 0 END) as active_repairs,
            SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as successful_repairs,
            SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_repairs,
            AVG(CASE WHEN status = 'COMPLETED' AND duration_ms IS NOT NULL THEN duration_ms ELSE NULL END) as avg_recovery_ms
        FROM repair_jobs
        """
    ) or {}

    total_objects = int(obj_stats.get("total_objects") or 0)
    degraded_objects = int(obj_stats.get("degraded_objects") or 0)
    corrupted_objects = int(obj_stats.get("corrupted_objects") or 0)

    if failed_nodes > 0 or corrupted_objects > 0 or degraded_objects > 0 or partitioned_nodes > 0:
        if active_nodes == 0 or corrupted_objects > 0:
            system_health = "CRITICAL"
        else:
            system_health = "DEGRADED"
    else:
        system_health = "HEALTHY"

    return {
        "system_health": system_health,
        "total_storage": total_storage,
        "used_storage": physical_storage,
        "available_storage": max(0, total_storage - physical_storage),
        "logical_storage": logical_storage,
        "physical_storage": physical_storage,
        "storage_overhead": storage_overhead,
        "replication_factor": settings.replication_factor,
        "total_nodes": total_nodes,
        "active_nodes": active_nodes,
        "failed_nodes": failed_nodes,
        "partitioned_nodes": partitioned_nodes,
        "total_objects": total_objects,
        "healthy_objects": int(obj_stats.get("healthy_objects") or 0),
        "degraded_objects": degraded_objects,
        "corrupted_objects": corrupted_objects,
        "total_replicas": int(rep_stats.get("total_replicas") or 0),
        "healthy_replicas": int(rep_stats.get("healthy_replicas") or 0),
        "corrupted_replicas": int(rep_stats.get("corrupted_replicas") or 0),
        "active_repairs": int(repair_stats.get("active_repairs") or 0),
        "successful_repairs": int(repair_stats.get("successful_repairs") or 0),
        "failed_repairs": int(repair_stats.get("failed_repairs") or 0),
        "average_recovery_time_ms": round(float(repair_stats.get("avg_recovery_ms") or 0.0), 2),
        "settings": settings.to_dict(),
    }
