# NexStore VAULT — Replication, Placement & Consistency Model

This document explains the configurable replication strategy, capacity-aware node placement algorithm, replica version consistency, optimistic concurrency control (OCC), and authoritative replica selection in **NexStore VAULT**.

---

## 1. Configurable Replication Strategy

NexStore VAULT enforces redundant storage across multiple independent storage nodes using a configurable **Replication Factor ($RF$)**:

- **Cluster-Wide Default (`REPLICATION_FACTOR`)**: Configured via `.env` (default `RF = 3`) and dynamically adjustable at runtime via `PUT /api/system/settings`.
- **Per-Object Override**: Clients can specify a custom `replication_factor` (`1` to `N` healthy nodes) during `POST /api/files/upload`.
- **Strict Admission Validation**: Before accepting a write or configuration update, `validate_and_select_nodes()` verifies that the cluster currently has at least $RF$ nodes where:
  $$\text{status} = \texttt{ONLINE} \quad \land \quad \text{network\_status} = \texttt{CONNECTED} \quad \land \quad (\text{capacity} - \text{used\_capacity}) \ge \text{object\_size}$$
  If fewer than $RF$ nodes satisfy these criteria, the upload fails fast with `HTTP 400 INSUFFICIENT_STORAGE_NODES` (`InsufficientNodesError`), preventing silent under-replication during ingestion.

---

## 2. Smart Placement Algorithm (`PlacementEngine`)

Implemented in [`backend/storage/placement.py`](file:///d:/hackthon%20antigravity/backend/storage/placement.py), the `PlacementEngine` guarantees that:
1. **Fault Domain Separation**: No two replicas of the same object are ever placed on the same storage node (`exclude_node_ids`).
2. **Health & Reachability Filtering**: Only nodes with `status == 'ONLINE'` and `network_status == 'CONNECTED'` are eligible candidates.
3. **Capacity Guard**: Candidate nodes must have `free_space = capacity - used_capacity >= object_size`.
4. **Utilization-Balanced Ranking**: Eligible candidates are scored by their current storage utilization ratio:
   $$U(n) = \frac{\text{used\_capacity}(n)}{\max(1, \text{capacity}(n))}$$
   Candidates are sorted in ascending order of $(\text{round}(U(n), 4), \text{node\_id})$ and the top $K = RF$ nodes are chosen.

### Placement Example
- **Upload #1 (`fileA.bin`, `RF=3`)**: All 5 nodes (`node1`..`node5`) have $U(n) = 0.0$. Ties break deterministically by `node_id`, selecting `node1`, `node2`, `node3`.
- **Upload #2 (`fileB.bin`, `RF=3`)**: `node4` and `node5` still have $U(n) = 0.0$, while `node1`..`node3` have $U(n) > 0$. The engine selects `node4`, `node5`, and `node1`—automatically balancing storage across all 5 nodes.

---

## 3. Replica Version Consistency

When an existing object is updated (either by re-uploading with the same `object_id` or matching `filename`), NexStore VAULT maintains strict version metadata across both the `objects` table and the `replicas` table:

1. **Monotonic Version Increment**:
   $$v_{\text{new}} = v_{\text{current}} + 1$$
2. **Coordinated Replica Update**:
   - All online replicas selected for the write receive the new binary payload, the new SHA-256 `checksum`, and `version = v_new`.
   - If a node previously holding a `v1` replica was temporarily `PARTITIONED` or `OFFLINE` during the `v2` write, its stored replica remains at `version = 1` while the authoritative object metadata advances to `version = 2`.
3. **Stale Replica Detection (`ReplicaStatus.STALE`)**:
   When `ConsistencyManager.check_object_consistency(object_id)` or `reconcile_node_replicas(node_id)` inspects a replica where:
   $$\text{replica.version} < \text{object.version}$$
   the replica is immediately flagged as `STALE` and either overwritten from the authoritative `v2` replica or pruned if $RF$ is already satisfied on other nodes.

---

## 4. Optimistic Concurrency Control (OCC) & Locking

NexStore VAULT combines two layers of concurrency protection in [`backend/concurrency/`](file:///d:/hackthon%20antigravity/backend/concurrency/locks.py):

### 4.1 Per-Object Reader-Writer Locks (`LockManager`)
- **Multiple Concurrent Readers**: `lock_manager.acquire_read(object_id)` allows multiple simultaneous downloads and integrity scans of the same object without blocking each other.
- **Exclusive Writers**: `lock_manager.acquire_write(lock_key)` serializes concurrent uploads, corruptions, or deletes targeting the same object, guaranteeing that metadata updates and physical file writes never interleave.

### 4.2 Optimistic Concurrency Control (`validate_expected_version`)
Clients performing conditional updates can supply `expected_version` in `POST /api/files/upload`.
- If `expected_version == current_version`, the update proceeds and increments the version to `current_version + 1`.
- If `expected_version != current_version`, the server rejects the write with `HTTP 409 Conflict` (`VERSION_CONFLICT`), preventing lost updates in multi-writer environments.

---

## 5. Authoritative Replica Selection

During read failover, self-healing repair, and post-partition reconciliation, `ConsistencyManager.select_authoritative_replica(object_id)` ([`backend/replication/consistency.py`](file:///d:/hackthon%20antigravity/backend/replication/consistency.py)) selects the canonical source of truth using a zero-trust verification rule:

1. Query all replicas of `object_id` hosted on nodes where `status = 'ONLINE'` and `network_status = 'CONNECTED'`, ordered by `version DESC, node_id ASC`.
2. For each candidate replica:
   - Verify the physical file exists on disk (`storage_nodes/{node_id}/data/{object_id}`).
   - Compute the live SHA-256 digest directly from the disk file (`compute_sha256_file`).
   - Compare `actual_sha256 == object.checksum` **AND** `replica.version == object.version`.
3. The first replica passing both cryptographic and version verification is returned as the **Authoritative Replica**. Stale or corrupted replicas can **never** be selected as a repair source.
