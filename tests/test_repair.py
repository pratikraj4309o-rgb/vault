import io
from backend.storage.object_store import object_store


def test_automatic_repair_on_node_failure_replicates_to_replacement_node(client):
    payload = b"Self-healing replacement replica test payload"
    up = client.post(
        "/api/files/upload",
        files={"file": ("self_heal.bin", io.BytesIO(payload), "application/octet-stream")},
        data={"replication_factor": "3"},
    ).json()["object"]
    obj_id = up["object_id"]
    initial_nodes = {r["node_id"] for r in up["replicas"]}
    failed_node = sorted(initial_nodes)[0]

    # Trigger node failure with auto_repair=true
    fail_res = client.post(f"/api/nodes/{failed_node}/fail?auto_repair=true")
    assert fail_res.status_code == 200

    # Verify object is restored to HEALTHY with 3 healthy replicas including a new replacement node
    meta = client.get(f"/api/files/{obj_id}/metadata").json()
    assert meta["status"] == "HEALTHY"
    assert meta["healthy_replicas"] == 3
    new_healthy_nodes = {
        r["node_id"] for r in meta["replicas"] if r["status"] == "HEALTHY"
    }
    assert failed_node not in new_healthy_nodes
    assert len(new_healthy_nodes) == 3

    repairs = client.get("/api/repairs").json()["repairs"]
    completed_jobs = [j for j in repairs if j["object_id"] == obj_id and j["status"] == "COMPLETED"]
    assert len(completed_jobs) >= 1
    assert completed_jobs[0]["duration_ms"] >= 1


def test_in_place_repair_of_corrupted_replica_and_retry(client):
    payload = b"In-place corruption repair payload"
    up = client.post(
        "/api/files/upload",
        files={"file": ("inplace.dat", io.BytesIO(payload), "application/octet-stream")},
        data={"replication_factor": "3"},
    ).json()["object"]
    obj_id = up["object_id"]
    corrupted_node = up["replicas"][-1]["node_id"]

    # Corrupt without auto-repair first
    c_res = client.post(
        f"/api/files/{obj_id}/corrupt",
        json={"node_id": corrupted_node, "auto_repair": False},
    )
    assert c_res.status_code == 200

    # Trigger pending repairs via API
    run_res = client.post("/api/repairs/run")
    assert run_res.status_code == 200
    assert run_res.json()["processed"] >= 1

    # Physical bytes on corrupted_node must now be restored to original payload
    assert object_store.read_replica_bytes(corrupted_node, obj_id) == payload

    # Test retry endpoint on the completed repair job
    job_id = run_res.json()["jobs"][0]["repair_id"]
    retry_res = client.post(f"/api/repairs/{job_id}/retry")
    assert retry_res.status_code == 200
    assert retry_res.json()["repair"]["status"] == "COMPLETED"
