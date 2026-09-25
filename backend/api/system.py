from fastapi import APIRouter
from backend.concurrency.request_manager import request_manager
from backend.config import settings
from backend.database import db
from backend.exceptions import InvalidConfigurationError
from backend.models import EventType
from backend.schemas import SettingsUpdateRequest
from backend.storage.node_manager import node_manager
from backend.storage.storage_metrics import get_cluster_metrics

router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/stats")
async def get_system_stats():
    metrics = get_cluster_metrics()
    metrics["concurrency"] = request_manager.get_stats()
    return metrics


@router.get("/settings")
async def get_settings():
    return settings.to_dict()


@router.post("/settings")
@router.put("/settings")
async def update_settings(payload: SettingsUpdateRequest):
    healthy_nodes = node_manager.get_healthy_nodes()
    healthy_count = len(healthy_nodes)

    if payload.replication_factor is not None:
        if payload.replication_factor < 1:
            raise InvalidConfigurationError("replication_factor must be >= 1")
        if payload.replication_factor > healthy_count:
            raise InvalidConfigurationError(
                f"replication_factor ({payload.replication_factor}) cannot exceed healthy node count ({healthy_count})"
            )
        settings.replication_factor = payload.replication_factor

    if payload.health_check_interval is not None:
        settings.health_check_interval = payload.health_check_interval

    if payload.repair_interval is not None:
        settings.repair_interval = payload.repair_interval

    if payload.integrity_check_interval is not None:
        settings.integrity_check_interval = payload.integrity_check_interval

    if payload.rebalance_threshold is not None:
        settings.rebalance_threshold = payload.rebalance_threshold

    if payload.max_storage_per_node is not None:
        settings.max_storage_per_node = payload.max_storage_per_node
        with db.transaction() as conn:
            conn.execute("UPDATE nodes SET capacity = ?", (settings.max_storage_per_node,))

    if payload.auto_scale_enabled is not None:
        settings.auto_scale_enabled = payload.auto_scale_enabled

    db.log_activity(
        EventType.SETTINGS_UPDATED.value,
        f"Cluster configuration updated (RF={settings.replication_factor}, AutoScale={settings.auto_scale_enabled}, RebalanceThreshold={settings.rebalance_threshold}%)",
        severity="INFO",
    )
    return {"status": "updated", "settings": settings.to_dict()}
