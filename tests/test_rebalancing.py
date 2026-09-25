import io
from backend.storage.node_manager import node_manager
from backend.storage.object_store import object_store


def test_cluster_rebalancing_migrates_replicas_and_verifies_checksum(client):
    # Temporarily partition node4 and node5 so all uploads land strictly on node1, node2, node3
    node_manager.partition_node("node4")
    node_manager.partition_node("node5")

    for i in range(3):
        client.post(
            "/api/files/upload",
            files={"file": (f"heavy_{i}.bin", io.BytesIO(b"X" * 4096), "application/octet-stream")},
            data={"replication_factor": "3"},
        )

    # Reconnect node4 and node5 — they currently hold 0 replicas while node1..3 hold 3 replicas each
    node_manager.reconnect_node("node4")
    node_manager.reconnect_node("node5")

    before_n4 = node_manager.get_node("node4")["replica_count"]
    before_n5 = node_manager.get_node("node5")["replica_count"]
    assert before_n4 == 0 and before_n5 == 0

    # Trigger rebalancing via API
    reb_res = client.post("/api/rebalance")
    assert reb_res.status_code == 200
    reb_body = reb_res.json()
    assert reb_body["status"] == "COMPLETED"
    assert reb_body["objects_moved"] >= 1
    assert len(reb_body["movements"]) >= 1

    for move in reb_body["movements"]:
        assert move["checksum_verified"] is True

    last_move = reb_body["movements"][-1]
    assert object_store.get_replica_path(last_move["to_node"], last_move["object_id"]).exists()
    assert not object_store.get_replica_path(last_move["from_node"], last_move["object_id"]).exists()

    after_n4 = node_manager.get_node("node4")["replica_count"]
    after_n5 = node_manager.get_node("node5")["replica_count"]
    assert (after_n4 + after_n5) >= 2

    status_res = client.get("/api/rebalance/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "COMPLETED"
