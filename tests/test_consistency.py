import io
from backend.database import db
from backend.replication.consistency import consistency_manager
from backend.storage.object_store import object_store


def test_stale_replica_detection_and_reconciliation_after_partition_update(client):
    v1_data = b"Document version 1 before network partition"
    v2_data = b"Document version 2 updated while node1 was partitioned"

    # 1. Upload v1 across 3 nodes
    up_v1 = client.post(
        "/api/files/upload",
        files={"file": ("contract.pdf", io.BytesIO(v1_data), "application/pdf")},
        data={"replication_factor": "3"},
    ).json()["object"]
    obj_id = up_v1["object_id"]
    partitioned_node = sorted(r["node_id"] for r in up_v1["replicas"])[0]

    # 2. Partition partitioned_node so it misses the v2 update
    client.post(f"/api/nodes/{partitioned_node}/partition")

    # 3. Upload v2 of the same object (replicated to online nodes with RF=2 so partitioned_node replica is still needed for RF=3)
    up_v2 = client.post(
        "/api/files/upload",
        files={"file": ("contract.pdf", io.BytesIO(v2_data), "application/pdf")},
        data={"object_id": obj_id, "replication_factor": "2"},
    ).json()["object"]
    assert up_v2["version"] == 2

    # Increase target replication_factor back to 3 so partitioned_node's stale v1 replica is resynced rather than pruned
    with db.transaction() as conn:
        conn.execute("UPDATE objects SET replication_factor = 3 WHERE object_id = ?", (obj_id,))

    # 4. Bring partitioned_node ONLINE manually to test consistency_manager.check_object_consistency() detecting STALE v1
    with db.transaction() as conn:
        conn.execute(
            "UPDATE nodes SET status = 'ONLINE', network_status = 'CONNECTED' WHERE node_id = ?",
            (partitioned_node,),
        )

    check = consistency_manager.check_object_consistency(obj_id)
    assert check["consistent"] is False
    assert partitioned_node in check["stale_replicas"]

    # 5. Reconnect / reconcile partitioned_node -> resyncs v2 bytes & checksum from authoritative replica
    rec = client.post(f"/api/nodes/{partitioned_node}/reconnect")
    assert rec.status_code == 200

    rep_row = db.fetch_one(
        "SELECT * FROM replicas WHERE object_id = ? AND node_id = ?",
        (obj_id, partitioned_node),
    )
    assert rep_row["status"] == "HEALTHY"
    assert rep_row["version"] == 2
    assert object_store.read_replica_bytes(partitioned_node, obj_id) == v2_data
