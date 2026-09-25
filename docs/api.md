# NexStore VAULT — Complete REST API Reference

Base URL: `http://127.0.0.1:8000`  
Interactive OpenAPI / Swagger UI: `http://127.0.0.1:8000/docs`

All endpoints return `application/json` (except `GET /api/files/{object_id}` when downloading binary file content). Domain errors return structured JSON payloads:

```json
{
  "error": "INSUFFICIENT_STORAGE_NODES",
  "detail": "Replication factor 4 requires 4 healthy nodes, but only 3 available.",
  "status_code": 400
}
```

---

## 1. Health & System Telemetry

### `GET /api/health`
Returns cluster-wide health status and node state counts.

**cURL Request:**
```bash
curl -s http://127.0.0.1:8000/api/health
```

**Response (`200 OK`):**
```json
{
  "status": "healthy",
  "nodes": 5,
  "healthy_nodes": 5,
  "failed_nodes": 0,
  "partitioned_nodes": 0,
  "timed_out_detected": 0
}
```

---

### `GET /api/system/stats`
Returns comprehensive cluster metrics, capacity utilization, replica health counts, repair performance (`avg_repair_duration_ms`), data integrity percentage, and active concurrency counters.

**cURL Request:**
```bash
curl -s http://127.0.0.1:8000/api/system/stats
```

**Response (`200 OK`):**
```json
{
  "cluster_status": "HEALTHY",
  "total_nodes": 5,
  "online_nodes": 5,
  "failed_nodes": 0,
  "partitioned_nodes": 0,
  "total_objects": 2,
  "healthy_objects": 2,
  "degraded_objects": 0,
  "corrupted_objects": 0,
  "unavailable_objects": 0,
  "total_replicas": 6,
  "healthy_replicas": 6,
  "corrupted_replicas": 0,
  "missing_replicas": 0,
  "total_capacity_bytes": 53687091200,
  "used_capacity_bytes": 24576,
  "utilization_percent": 0.01,
  "replication_factor": 3,
  "data_integrity_percent": 100.0,
  "active_repairs": 0,
  "completed_repairs": 1,
  "avg_repair_duration_ms": 4,
  "concurrency": {
    "active_reads": 0,
    "active_writes": 0,
    "total_reads": 5,
    "total_writes": 2
  }
}
```

---

### `GET /api/system/settings` & `PUT /api/system/settings`
Retrieve or dynamically update runtime cluster settings (`replication_factor`, `rebalance_threshold`, `health_check_interval`, `repair_interval`, `integrity_check_interval`, `max_storage_per_node`).

**cURL Request:**
```bash
curl -X PUT http://127.0.0.1:8000/api/system/settings \
  -H "Content-Type: application/json" \
  -d '{"replication_factor": 3, "rebalance_threshold": 75}'
```

**Response (`200 OK`):**
```json
{
  "status": "updated",
  "settings": {
    "app_name": "NexStore VAULT",
    "host": "127.0.0.1",
    "port": 8000,
    "replication_factor": 3,
    "health_check_interval": 5,
    "heartbeat_timeout": 15,
    "repair_interval": 3,
    "integrity_check_interval": 30,
    "rebalance_threshold": 75,
    "max_storage_per_node": 10737418240,
    "node_count": 5
  }
}
```

---

## 2. Storage Node Management & Failure Simulation (`/api/nodes/*`)

### `GET /api/nodes`
Lists all storage nodes with capacity, utilization percentage, replica counts, and heartbeat status.

```bash
curl -s http://127.0.0.1:8000/api/nodes
```

### `GET /api/nodes/{node_id}`
Returns detailed metrics and all hosted replicas for a specific storage node (`node1`–`node5`).

```bash
curl -s http://127.0.0.1:8000/api/nodes/node1
```

### `POST /api/nodes/{node_id}/fail`
Simulates a catastrophic hardware failure on `{node_id}`. Marks hosted replicas `MISSING`, updates affected objects to `DEGRADED`, and automatically triggers self-healing replacement replication when `auto_repair=true` (default).

```bash
curl -X POST "http://127.0.0.1:8000/api/nodes/node1/fail?auto_repair=true"
```

**Response (`200 OK`):**
```json
{
  "node": {
    "node_id": "node1",
    "status": "FAILED",
    "network_status": "DISCONNECTED",
    "health_status": "CRITICAL"
  },
  "affected_objects": ["obj_8a4f21c90e1b"],
  "scheduled_repairs": [
    {
      "repair_id": "repjob_91c4a802",
      "object_id": "obj_8a4f21c90e1b",
      "failed_node_id": "node1",
      "status": "QUEUED"
    }
  ]
}
```

### `POST /api/nodes/{node_id}/restore`
Restores a `FAILED` node to `ONLINE`, reconciles its stored replicas against authoritative object versions/checksums, and prunes surplus replicas if $RF$ was already satisfied on replacement nodes.

```bash
curl -X POST http://127.0.0.1:8000/api/nodes/node1/restore
```

### `POST /api/nodes/{node_id}/partition`
Simulates a temporary network partition (`status = PARTITIONED`, `network_status = PARTITIONED`). Replicas on the node become `UNAVAILABLE` without being permanently destroyed.

```bash
curl -X POST http://127.0.0.1:8000/api/nodes/node2/partition
```

### `POST /api/nodes/{node_id}/reconnect`
Heals a network partition on `{node_id}`, compares replica versions and SHA-256 digests, and automatically synchronizes any `STALE` or `CORRUPTED` replicas from an authoritative node.

```bash
curl -X POST http://127.0.0.1:8000/api/nodes/node2/reconnect
```

---

## 3. Object & File Operations (`/api/files/*`)

### `GET /api/files`
Lists all stored objects along with their replica placement arrays and health metrics.

```bash
curl -s http://127.0.0.1:8000/api/files
```

---

### `POST /api/files/upload`
Uploads a new object or updates an existing object (`multipart/form-data`). Supports optional `replication_factor`, `object_id`, and `expected_version` (for Optimistic Concurrency Control).

**cURL Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/files/upload \
  -F "file=@report.pdf" \
  -F "replication_factor=3"
```

**Response (`200 OK`):**
```json
{
  "status": "COMPLETED",
  "object": {
    "object_id": "obj_8a4f21c90e1b",
    "filename": "report.pdf",
    "size": 14280,
    "content_type": "application/pdf",
    "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "version": 1,
    "replication_factor": 3,
    "current_replicas": 3,
    "healthy_replicas": 3,
    "missing_replicas": 0,
    "status": "HEALTHY",
    "replicas": [
      {"replica_id": "rep_1", "node_id": "node1", "status": "HEALTHY", "version": 1},
      {"replica_id": "rep_2", "node_id": "node2", "status": "HEALTHY", "version": 1},
      {"replica_id": "rep_3", "node_id": "node3", "status": "HEALTHY", "version": 1}
    ]
  },
  "pipeline": {
    "uploading": "COMPLETED",
    "hashing": "COMPLETED",
    "replicating": "COMPLETED",
    "verifying": "COMPLETED"
  }
}
```

---

### `GET /api/files/{object_id}`
Downloads the binary object payload after verifying its SHA-256 digest on disk. Automatically fails over to a healthy replica if the primary copy is corrupted or offline. Pass `?metadata_only=true` to return JSON metadata instead.

**cURL Request:**
```bash
curl -i http://127.0.0.1:8000/api/files/obj_8a4f21c90e1b -o downloaded_report.pdf
```

**Response Headers (`200 OK`):**
```http
HTTP/1.1 200 OK
Content-Disposition: attachment; filename="report.pdf"
X-Vault-Object-Id: obj_8a4f21c90e1b
X-Vault-Served-Node: node1
X-Vault-Checksum: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
X-Vault-Version: 1
```

---

### `GET /api/files/{object_id}/metadata` & `GET /api/files/{object_id}/replicas`
Returns full object metadata or replica breakdown for `{object_id}`.

```bash
curl -s http://127.0.0.1:8000/api/files/obj_8a4f21c90e1b/replicas
```

---

### `POST /api/files/{object_id}/verify`
Performs an immediate on-disk SHA-256 integrity check across all replicas of `{object_id}` and automatically queues repairs for any corrupted or missing copies (`queue_repair=true`).

```bash
curl -X POST "http://127.0.0.1:8000/api/files/obj_8a4f21c90e1b/verify?queue_repair=true"
```

---

### `POST /api/files/{object_id}/corrupt`
Chaos engineering endpoint that tampers with the physical replica file on disk (simulating silent bit-rot) on a specified `node_id` (or the first healthy replica if omitted).

```bash
curl -X POST http://127.0.0.1:8000/api/files/obj_8a4f21c90e1b/corrupt \
  -H "Content-Type: application/json" \
  -d '{"node_id": "node1", "auto_repair": false}'
```

---

### `DELETE /api/files/{object_id}`
Deletes the object metadata and removes all physical replica files across all storage nodes.

```bash
curl -X DELETE http://127.0.0.1:8000/api/files/obj_8a4f21c90e1b
```

---

## 4. Replica, Repair, Rebalance & Integrity Endpoints

### `GET /api/replicas`
Lists all replicas across the entire cluster.

```bash
curl -s http://127.0.0.1:8000/api/replicas
```

### `GET /api/repairs`
Lists all queued, running, and completed self-healing repair jobs with `duration_ms` and source/target node telemetry.

```bash
curl -s http://127.0.0.1:8000/api/repairs
```

### `POST /api/repairs/run`
Immediately executes all pending repair jobs and scans for any degraded objects needing repair.

```bash
curl -X POST http://127.0.0.1:8000/api/repairs/run
```

### `POST /api/repairs/{repair_id}/retry`
Re-queues and executes a specific repair job by ID.

```bash
curl -X POST http://127.0.0.1:8000/api/repairs/repjob_91c4a802/retry
```

### `POST /api/rebalance` & `GET /api/rebalance/status`
Triggers verified cluster storage rebalancing across healthy nodes or queries the latest rebalance telemetry.

```bash
curl -X POST http://127.0.0.1:8000/api/rebalance
curl -s http://127.0.0.1:8000/api/rebalance/status
```

### `POST /api/integrity/scan`
Executes a full-cluster cryptographic SHA-256 scrub across all stored objects and replicas, marking any tampered files `CORRUPTED` and scheduling self-healing repairs.

```bash
curl -X POST http://127.0.0.1:8000/api/integrity/scan
```

### `GET /api/activity`
Returns chronological cluster audit events (`limit=50` by default, up to `500`).

```bash
curl -s "http://127.0.0.1:8000/api/activity?limit=50"
```
