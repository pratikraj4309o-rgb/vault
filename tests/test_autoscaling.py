import io
from backend.services.object_service import object_service


def test_auto_scale_spawns_node6_when_healthy_nodes_drop_below_rf(client):
    """When healthy nodes drop below replication_factor (e.g. 3 nodes fail), VAULT auto-scales node6 and repairs onto it."""
    res = client.post(
        "/api/files/upload",
        files={"file": ("autoscale_dataset.bin", io.BytesIO(b"critical-distributed-payload" * 100), "application/octet-stream")},
        data={"replication_factor": "3"},
    )
    assert res.status_code == 200
    obj_id = res.json()["object"]["object_id"]

    # Fail node4 and node5 first (standby nodes), then fail node2 (which holds a replica)
    client.post("/api/nodes/node4/fail?auto_repair=false")
    client.post("/api/nodes/node5/fail?auto_repair=false")

    # Now only node1, node2, node3 are online. Failing node2 with auto_repair=true leaves only 2 online nodes (< RF=3),
    # triggering automatic provisioning of node6 and repairing the replica onto node6!
    fail_res = client.post("/api/nodes/node2/fail?auto_repair=true")
    assert fail_res.status_code == 200
    payload = fail_res.json()

    assert len(payload["auto_scaled_nodes"]) == 1
    assert payload["auto_scaled_nodes"][0]["node_id"] == "node6"
    assert payload["auto_scaled_nodes"][0]["status"] == "ONLINE"

    updated_obj = object_service.get_object(obj_id)
    assert updated_obj["status"] == "HEALTHY"
    assert updated_obj["healthy_replicas"] == 3
    healthy_node_ids = {
        r["node_id"] for r in updated_obj["replicas"] if r["status"] == "HEALTHY" and r["node_status"] == "ONLINE"
    }
    assert "node6" in healthy_node_ids


def test_force_autoscale_on_single_node_failure_spawns_replacement_node(client):
    """When force_autoscale=true is passed on node failure, VAULT immediately spawns node6 and repairs onto node6."""
    res = client.post(
        "/api/files/upload",
        files={"file": ("instant_scale.bin", io.BytesIO(b"instant-autoscale-test" * 50), "application/octet-stream")},
        data={"replication_factor": "3"},
    )
    assert res.status_code == 200
    obj_id = res.json()["object"]["object_id"]

    fail_res = client.post("/api/nodes/node2/fail?auto_repair=true&force_autoscale=true")
    assert fail_res.status_code == 200
    data = fail_res.json()
    assert len(data["auto_scaled_nodes"]) == 1
    assert data["auto_scaled_nodes"][0]["node_id"] == "node6"

    updated_obj = object_service.get_object(obj_id)
    assert updated_obj["status"] == "HEALTHY"
    assert updated_obj["healthy_replicas"] == 3
    healthy_node_ids = {
        r["node_id"] for r in updated_obj["replicas"] if r["status"] == "HEALTHY" and r["node_status"] == "ONLINE"
    }
    assert healthy_node_ids == {"node1", "node3", "node6"}


def test_manual_provision_and_decommission_node_api(client):
    """Verifies POST /api/nodes/provision and DELETE /api/nodes/{node_id}."""
    prov_res = client.post("/api/nodes/provision", json={"reason": "Scale out test"})
    assert prov_res.status_code == 200
    new_node = prov_res.json()["node"]
    assert new_node["node_id"] == "node6"
    assert new_node["status"] == "ONLINE"

    nodes_list = client.get("/api/nodes").json()["nodes"]
    assert len(nodes_list) == 6

    del_res = client.delete("/api/nodes/node6")
    assert del_res.status_code == 200
    assert del_res.json()["decommissioned"] is True

    nodes_after = client.get("/api/nodes").json()["nodes"]
    assert len(nodes_after) == 5
