from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class NodeResponse(BaseModel):
    node_id: str
    status: str
    capacity: int
    used_capacity: int
    utilization_percent: float = 0.0
    object_count: int
    replica_count: int = 0
    last_heartbeat: str
    network_status: str
    health_status: str


class ReplicaResponse(BaseModel):
    replica_id: str
    object_id: str
    filename: Optional[str] = None
    node_id: str
    checksum: str
    actual_checksum: Optional[str] = None
    expected_checksum: Optional[str] = None
    version: int
    status: str
    node_status: Optional[str] = None
    created_at: str
    updated_at: str


class ObjectResponse(BaseModel):
    object_id: str
    filename: str
    size: int
    content_type: str
    checksum: str
    version: int
    created_at: str
    updated_at: str
    replication_factor: int
    current_replicas: int = 0
    healthy_replicas: int = 0
    missing_replicas: int = 0
    status: str
    integrity: str = "VERIFIED"
    replicas: List[ReplicaResponse] = []


class RepairJobResponse(BaseModel):
    repair_id: str
    object_id: str
    filename: Optional[str] = None
    source_node_id: Optional[str] = None
    failed_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    reason: str
    status: str
    progress: int
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None


class ActivityEventResponse(BaseModel):
    event_id: int
    event_type: str
    message: str
    object_id: Optional[str] = None
    node_id: Optional[str] = None
    severity: str = "INFO"
    details: Optional[str] = None
    created_at: str


class SettingsUpdateRequest(BaseModel):
    replication_factor: Optional[int] = Field(None, ge=1)
    health_check_interval: Optional[int] = Field(None, ge=1)
    repair_interval: Optional[int] = Field(None, ge=1)
    integrity_check_interval: Optional[int] = Field(None, ge=1)
    rebalance_threshold: Optional[int] = Field(None, ge=10, le=99)
    max_storage_per_node: Optional[int] = Field(None, ge=1024)
    auto_scale_enabled: Optional[bool] = None


class CorruptReplicaRequest(BaseModel):
    node_id: Optional[str] = None
    replica_id: Optional[str] = None
    auto_repair: bool = False


class SystemStatsResponse(BaseModel):
    system_health: str
    total_storage: int
    used_storage: int
    available_storage: int
    logical_storage: int
    physical_storage: int
    storage_overhead: int
    replication_factor: int
    total_nodes: int
    active_nodes: int
    failed_nodes: int
    partitioned_nodes: int
    total_objects: int
    healthy_objects: int
    degraded_objects: int
    corrupted_objects: int
    total_replicas: int
    healthy_replicas: int
    corrupted_replicas: int
    active_repairs: int
    successful_repairs: int
    failed_repairs: int
    average_recovery_time_ms: float
    settings: Dict[str, Any]
