import io
from backend.database import db
from backend.storage.object_store import object_store


def test_fail_node_marks_replicas_missing_and_object_degraded(client):
    data = b"High availability mission logs"
    up = client.post(
        "/api/files/upload",
        files={"file": ("mission.log", io.BytesIO(data), "text/plain")},
        data={"replication_factor": "3"},
    ).json()["object"]
    obj_id = up["object_id"]
    replica_nodes = [r["node_id"] for r in up["replicas"]]
    failed_node = replica_nodes[0]
    surviving_nodes = replica_nodes[1:]

    # Fail node without auto_repair first so we can inspect the intermediate DEGRADED/MISSING state
    fail_res = client.post(f"/api/nodes/{failed_node}/fail?auto_repair=false")
    assert fail_res.status_code == 200
    fail_body = fail_res.json()

    assert fail_body["node"]["status"] == "FAILED"
    assert obj_id in fail_body["affected_objects"]

    # Check replica on failed_node is marked MISSING
    rep_row = db.fetch_one(
        "SELECT * FROM replicas WHERE object_id = ? AND node_id = ?",
        (obj_id, failed_node),
    )
    assert rep_row["status"] == "MISSING"

    # Check object is marked DEGRADED
    obj_row = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (obj_id,))
    assert obj_row["status"] == "DEGRADED"

    # Other nodes' physical files remain completely intact
    for survivor in surviving_nodes:
        assert object_store.read_replica_bytes(survivor, obj_id) == data
