from enum import Enum
from dataclasses import dataclass
from typing import Optional


class NodeStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
    PARTITIONED = "PARTITIONED"
    REBALANCING = "REBALANCING"


class ObjectStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    REPAIRING = "REPAIRING"
    CORRUPTED = "CORRUPTED"
    UNAVAILABLE = "UNAVAILABLE"
    REBALANCING = "REBALANCING"


class ReplicaStatus(str, Enum):
    HEALTHY = "HEALTHY"
    MISSING = "MISSING"
    CORRUPTED = "CORRUPTED"
    STALE = "STALE"
    REPAIRING = "REPAIRING"
    UNAVAILABLE = "UNAVAILABLE"


class RepairStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EventType(str, Enum):
    OBJECT_UPLOADED = "OBJECT_UPLOADED"
    OBJECT_DOWNLOADED = "OBJECT_DOWNLOADED"
    OBJECT_DELETED = "OBJECT_DELETED"
    REPLICA_CREATED = "REPLICA_CREATED"
    REPLICA_DELETED = "REPLICA_DELETED"
    NODE_FAILED = "NODE_FAILED"
    NODE_RECOVERED = "NODE_RECOVERED"
    REPAIR_STARTED = "REPAIR_STARTED"
    REPAIR_COMPLETED = "REPAIR_COMPLETED"
    REPAIR_FAILED = "REPAIR_FAILED"
    CHECKSUM_VERIFIED = "CHECKSUM_VERIFIED"
    CORRUPTION_DETECTED = "CORRUPTION_DETECTED"
    REBALANCE_STARTED = "REBALANCE_STARTED"
    REBALANCE_COMPLETED = "REBALANCE_COMPLETED"
    NETWORK_PARTITION = "NETWORK_PARTITION"
    NETWORK_RECONNECTED = "NETWORK_RECONNECTED"
    SETTINGS_UPDATED = "SETTINGS_UPDATED"
    NODE_PROVISIONED = "NODE_PROVISIONED"
    AUTO_SCALED = "AUTO_SCALED"


@dataclass
class NodeModel:
    node_id: str
    status: str
    capacity: int
    used_capacity: int
    object_count: int
    last_heartbeat: str
    network_status: str
    health_status: str


@dataclass
class ObjectModel:
    object_id: str
    filename: str
    size: int
    content_type: str
    checksum: str
    version: int
    created_at: str
    updated_at: str
    replication_factor: int
    status: str


@dataclass
class ReplicaModel:
    replica_id: str
    object_id: str
    node_id: str
    checksum: str
    version: int
    status: str
    created_at: str
    updated_at: str


@dataclass
class RepairJobModel:
    repair_id: str
    object_id: str
    source_node_id: Optional[str]
    failed_node_id: Optional[str]
    target_node_id: Optional[str]
    reason: str
    status: str
    progress: int
    started_at: str
    completed_at: Optional[str]
    duration_ms: Optional[int]
    error_message: Optional[str]
