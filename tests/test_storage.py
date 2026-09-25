import pytest
from backend.exceptions import InvalidConfigurationError
from backend.storage.node_manager import node_manager
from backend.storage.object_store import object_store


def test_five_storage_nodes_initialized(client):
    res = client.get("/api/nodes")
    assert res.status_code == 200
    payload = res.json()
    assert payload["count"] == 5
    node_ids = [n["node_id"] for n in payload["nodes"]]
    assert node_ids == ["node1", "node2", "node3", "node4", "node5"]
    for node in payload["nodes"]:
        assert node["status"] == "ONLINE"
        assert node["network_status"] == "CONNECTED"
        assert node["capacity"] > 0
        assert node["used_capacity"] == 0
        assert (object_store.get_node_dir(node["node_id"]) / "node.json").exists()


def test_physical_directory_isolation_and_read_write():
    data = b"distributed-storage-block-001"
    sha = object_store.write_replica_bytes("node1", "obj_test1", data)
    assert len(sha) == 64

    n1_path = object_store.get_replica_path("node1", "obj_test1")
    n2_path = object_store.get_replica_path("node2", "obj_test1")
    assert n1_path.exists()
    assert not n2_path.exists()
    assert object_store.read_replica_bytes("node1", "obj_test1") == data

    node_manager.refresh_all_node_metrics()
    n1_info = node_manager.get_node("node1")
    n2_info = node_manager.get_node("node2")
    assert n1_info["used_capacity"] == len(data)
    assert n2_info["used_capacity"] == 0


def test_path_traversal_prevention():
    with pytest.raises(InvalidConfigurationError):
        object_store.get_node_dir("../evil_node")

    with pytest.raises(InvalidConfigurationError):
        object_store.get_replica_path("node1", "../../etc/passwd")
