import io
from backend.database import db
from backend.storage.object_store import object_store


def test_delete_file_cleans_replicas_metadata_and_logs_activity(client):
    payload = b"Temporary staging archive to be purged"
    up = client.post(
        "/api/files/upload",
        files={"file": ("staging.tar", io.BytesIO(payload), "application/x-tar")},
        data={"replication_factor": "3"},
    ).json()["object"]

    obj_id = up["object_id"]
    replica_nodes = [r["node_id"] for r in up["replicas"]]

    for n_id in replica_nodes:
        assert object_store.get_replica_path(n_id, obj_id).exists()

    del_res = client.delete(f"/api/files/{obj_id}")
    assert del_res.status_code == 200
    del_body = del_res.json()
    assert del_body["deleted"] is True
    assert del_body["replicas_removed"] == 3

    for n_id in replica_nodes:
        assert not object_store.get_replica_path(n_id, obj_id).exists()

    assert db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (obj_id,)) is None
    assert db.fetch_all("SELECT * FROM replicas WHERE object_id = ?", (obj_id,)) == []

    logs = db.fetch_all(
        "SELECT * FROM activity_logs WHERE object_id = ? AND event_type = 'OBJECT_DELETED'",
        (obj_id,),
    )
    assert len(logs) == 1

    get_after = client.get(f"/api/files/{obj_id}")
    assert get_after.status_code == 404
