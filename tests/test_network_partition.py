import io
from backend.database import db


def test_network_partition_preserves_metadata_and_reconciles_on_reconnect(client):
    data = b"Partition tolerance test vector"
    up = client.post(
        "/api/files/upload",
        files={"file": ("vector.bin", io.BytesIO(data), "application/octet-stream")},
        data={"replication_factor": "3"},
    ).json()["object"]
    obj_id = up["object_id"]
    part_node = up["replicas"][0]["node_id"]

    # Partition the node
    part_res = client.post(f"/api/nodes/{part_node}/partition")
    assert part_res.status_code == 200
    assert part_res.json()["node"]["status"] == "PARTITIONED"
    assert part_res.json()["node"]["network_status"] == "PARTITIONED"

    # Replica is marked UNAVAILABLE (not permanently deleted), metadata preserved
    rep_during = db.fetch_one(
        "SELECT * FROM replicas WHERE object_id = ? AND node_id = ?",
        (obj_id, part_node),
    )
    assert rep_during is not None
    assert rep_during["status"] == "UNAVAILABLE"

    # Reconnect the partitioned node
    rec_res = client.post(f"/api/nodes/{part_node}/reconnect")
    assert rec_res.status_code == 200
    rec_body = rec_res.json()
    assert rec_body["node"]["status"] == "ONLINE"
    assert rec_body["node"]["network_status"] == "CONNECTED"

    # Replica should be verified HEALTHY again and object restored to HEALTHY
    rep_after = db.fetch_one(
        "SELECT * FROM replicas WHERE object_id = ? AND node_id = ?",
        (obj_id, part_node),
    )
    assert rep_after["status"] == "HEALTHY"
    obj_after = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (obj_id,))
    assert obj_after["status"] == "HEALTHY"
