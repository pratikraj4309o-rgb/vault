# NexStore VAULT — System Architecture

This document details the layered architecture, component responsibilities, and end-to-end execution sequence diagrams for **NexStore VAULT**.

---

## 1. Layered Architecture Overview

NexStore VAULT is structured into five decoupled architectural layers:

```mermaid
flowchart TB
    subgraph L1["Layer 1: Client & Mission-Control Presentation"]
        SPA["Single-Page Web Dashboard (frontend/js/app.js)"]
        CLI["REST Clients / cURL / Automated Test Suite"]
    end

    subgraph L2["Layer 2: FastAPI HTTP Gateway & Concurrency Control"]
        API["REST API Routers (backend/api/*.py)"]
        ReqMgr["RequestManager (Active Read/Write Telemetry)"]
        LockMgr["LockManager (Per-Object Reader-Writer Locks)"]
        OCC["OCC Version Validator (validate_expected_version)"]
    end

    subgraph L3["Layer 3: Domain Orchestration & Storage Services"]
        UpSvc["UploadService"]
        DownSvc["DownloadService"]
        DelSvc["DeleteService"]
        ObjSvc["ObjectService"]
        RepMgr["RepairManager & RepairQueue"]
        Rebal["Rebalancer & Migration Engine"]
        Consist["ConsistencyManager"]
    end

    subgraph L4["Layer 4: Autonomous Background Workers"]
        W1["HealthWorker (Heartbeat & Timeout Detection)"]
        W2["RepairWorker (Self-Healing Execution Loop)"]
        W3["IntegrityWorker (Periodic SHA-256 Scrubbing)"]
        W4["RebalanceWorker (Utilization Threshold Monitor)"]
    end

    subgraph L5["Layer 5: Persistence & Physical Node Storage"]
        SQLite[("SQLite WAL Database (data/vault.db)")]
        FS["ObjectStore Atomic File Engine (storage_nodes/node1..node5)"]
    end

    SPA & CLI --> API
    API --> ReqMgr --> LockMgr --> OCC
    OCC --> UpSvc & DownSvc & DelSvc & ObjSvc
    API --> RepMgr & Rebal
    W1 & W2 & W3 & W4 --> RepMgr & Rebal & ObjSvc
    UpSvc & DownSvc & DelSvc & ObjSvc & RepMgr & Rebal & Consist --> SQLite
    UpSvc & DownSvc & DelSvc & ObjSvc & RepMgr & Rebal & Consist --> FS
```

---

## 2. Component Responsibilities

| Component | Module Path | Core Responsibility |
| :--- | :--- | :--- |
| **FastAPI Application & Lifespan** | [`backend/main.py`](file:///d:/hackthon%20antigravity/backend/main.py) | Initializes SQLite WAL schema, bootstraps the 5 storage nodes, spawns the 4 background `asyncio` workers, and mounts the REST routers and static SPA assets. |
| **DatabaseManager** | [`backend/database.py`](file:///d:/hackthon%20antigravity/backend/database.py) | Thread-safe SQLite connection manager configured with `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, and `RLock`-guarded transactional context managers. |
| **NodeManager** | [`backend/storage/node_manager.py`](file:///d:/hackthon%20antigravity/backend/storage/node_manager.py) | Manages physical node directories (`storage_nodes/node1..5`), node descriptors (`node.json`), capacity calculations, and state transitions (`ONLINE`, `FAILED`, `PARTITIONED`). |
| **ObjectStore** | [`backend/storage/object_store.py`](file:///d:/hackthon%20antigravity/backend/storage/object_store.py) | Performs atomic disk writes via temporary `.tmp` files, `os.fsync()`, and `os.replace()` to guarantee zero partial files on power loss or crash. |
| **PlacementEngine** | [`backend/storage/placement.py`](file:///d:/hackthon%20antigravity/backend/storage/placement.py) | Selects `K` distinct healthy, connected nodes with sufficient free space, prioritized by lowest storage utilization ratio. |
| **UploadService** | [`backend/services/upload_service.py`](file:///d:/hackthon%20antigravity/backend/services/upload_service.py) | Orchestrates filename sanitization, per-object write locking, OCC version checks, SHA-256 calculation, multi-node replica persistence, and post-write verification. |
| **DownloadService** | [`backend/services/download_service.py`](file:///d:/hackthon%20antigravity/backend/services/download_service.py) | Acquires shared read locks, verifies replica SHA-256 digests before returning bytes, transparently fails over on corruption/offline nodes, and queues background repairs. |
| **ConsistencyManager** | [`backend/replication/consistency.py`](file:///d:/hackthon%20antigravity/backend/replication/consistency.py) | Selects authoritative replicas (`highest version + matching SHA-256`) and reconciles nodes recovering from failure or network partitions. |
| **RepairManager & RepairQueue** | [`backend/repair/repair_manager.py`](file:///d:/hackthon%20antigravity/backend/repair/repair_manager.py) | Deduplicates repair jobs, executes in-place or replacement node copies, verifies SHA-256 digests, and records repair latency (`duration_ms`). |
| **Rebalancer** | [`backend/rebalancing/rebalancer.py`](file:///d:/hackthon%20antigravity/backend/rebalancing/rebalancer.py) | Redistributes replicas from high-utilization nodes to low-utilization nodes without dropping below the target replication factor. |

---

## 3. Sequence Diagrams

### 3.1 Fault-Tolerant Object Upload & Replication Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant API as POST /api/files/upload
    participant Lock as LockManager
    participant Place as PlacementEngine
    participant DB as SQLite WAL DB
    participant Store as ObjectStore (Nodes 1..N)

    Client->>API: Upload file (multipart/form-data, RF=3)
    API->>Lock: acquire_write(object_id / filename)
    API->>API: sanitize_filename() & compute_sha256_bytes(data)
    API->>DB: Check existing object & validate expected_version (OCC)
    API->>Place: select_nodes_for_object(required_count=3, object_size)
    Place-->>API: Selected [node1, node2, node3] (lowest utilization first)
    API->>DB: INSERT/UPDATE objects (status='HEALTHY', version=v)
    loop For each target node in [node1, node2, node3]
        API->>Store: write_replica_atomic(node_id, object_id, data)
        Note over Store: Write .tmp -> fsync -> os.replace()
        API->>Store: compute_sha256_file(replica_path)
        Store-->>API: Verified SHA-256 matches expected_checksum
        API->>DB: INSERT/UPDATE replicas (status='HEALTHY', version=v)
    end
    API->>DB: INSERT activity_logs (OBJECT_UPLOADED, CHECKSUM_VERIFIED)
    API->>Lock: release_write()
    API-->>Client: 200 OK (Object Metadata + 4-Stage Pipeline COMPLETED)
```

---

### 3.2 Verified Object Download & Zero-Downtime Read Failover Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant API as GET /api/files/{object_id}
    participant Down as DownloadService
    participant DB as SQLite WAL DB
    participant N1 as Node 1 (Corrupted Replica)
    participant N2 as Node 2 (Healthy Replica)
    participant Repair as RepairManager

    Client->>API: Request object download
    API->>Down: retrieve_object(object_id)
    Down->>DB: Fetch object metadata & candidate ONLINE replicas
    DB-->>Down: Expected SHA-256 + [node1, node2, node3]
    Down->>N1: compute_sha256_file(node1/data/{object_id})
    N1-->>Down: Actual SHA-256 != Expected SHA-256 (Bit-Rot Detected!)
    Down->>DB: UPDATE replicas SET status='CORRUPTED' (node1)
    Down->>DB: Log CORRUPTION_DETECTED event
    Note over Down,N2: Automatic Zero-Downtime Failover to Node 2
    Down->>N2: compute_sha256_file(node2/data/{object_id})
    N2-->>Down: Actual SHA-256 == Expected SHA-256 (Verified!)
    Down->>N2: read_replica_bytes(node2, object_id)
    Down->>Repair: evaluate_and_schedule_object_repairs(object_id)
    Repair->>DB: Enqueue QUEUED repair job for node1
    Down-->>API: (obj_metadata, served_node="node2", raw_bytes)
    API-->>Client: 200 OK Binary Stream (Header X-Vault-Served-Node: node2)
```

---

### 3.3 Autonomous Self-Healing Repair Sequence

```mermaid
sequenceDiagram
    autonumber
    participant Worker as RepairWorker / Trigger
    participant Mgr as RepairManager
    participant Cons as ConsistencyManager
    participant Place as PlacementEngine
    participant Store as ObjectStore
    participant DB as SQLite WAL DB

    Worker->>Mgr: process_pending_repairs()
    Mgr->>DB: Fetch QUEUED repair jobs
    loop For each RepairJob
        Mgr->>Cons: select_authoritative_replica(object_id)
        Cons-->>Mgr: Authoritative source (e.g., node2, highest version + verified SHA-256)
        alt Failed node is ONLINE (In-Place Repair for Bit-Rot/Stale)
            Mgr->>Mgr: target_node_id = failed_node_id (e.g., node1)
        else Failed node is FAILED (Replacement Node Repair)
            Mgr->>Place: select_nodes_for_object(count=1, exclude=existing_healthy)
            Place-->>Mgr: target_node_id = node4
        end
        Mgr->>DB: UPDATE repair_jobs SET status='RUNNING', progress=50
        Mgr->>Store: copy_replica_between_nodes(source_node, target_node, object_id)
        Store-->>Mgr: Computed SHA-256 of newly written target file
        Mgr->>DB: UPDATE repair_jobs SET status='VERIFYING', progress=85
        Mgr->>Mgr: Verify target SHA-256 == authoritative object checksum
        Mgr->>DB: Upsert replica as HEALTHY, mark repair COMPLETED (progress=100, duration_ms)
        Mgr->>DB: Refresh object status to HEALTHY & emit REPAIR_COMPLETED
    end
```

---

### 3.4 Verified Storage Rebalancing Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Admin as User / RebalanceWorker
    participant Reb as Rebalancer
    participant Mig as MigrationEngine (migrate_replica_safely)
    participant Store as ObjectStore
    participant DB as SQLite WAL DB

    Admin->>Reb: run_rebalance(force_balance=True)
    Reb->>DB: Rank healthy nodes by (utilization_percent, replica_count)
    Note over Reb: Identify heaviest node (Source) & lightest node (Target)
    Reb->>DB: Select candidate replica on Source not present on Target
    Reb->>Mig: migrate_replica_safely(replica_id, object_id, source, target, expected_sha)
    Mig->>Store: Step 1: Copy replica bytes (source -> target atomic .tmp write)
    Store-->>Mig: Return target SHA-256 checksum
    Mig->>Mig: Step 2: Verify target SHA-256 == expected_checksum
    Mig->>DB: Step 3: UPDATE replicas SET node_id=target, status='HEALTHY'
    Mig->>Store: Step 4: Delete old replica file from source node
    Mig->>DB: Refresh node capacity metrics & log REBALANCE_COMPLETED
    Reb-->>Admin: Return migration summary (objects_moved, bytes_moved, movements[])
```
