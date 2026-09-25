import io
import pytest
from backend.exceptions import InsufficientNodesError
from backend.services.upload_service import upload_service
from backend.storage.node_manager import node_manager


@pytest.mark.parametrize("rf", [1, 2, 3, 4, 5])
def test_configurable_replication_factor_distinct_nodes(client, rf):
    data = f"Replication factor {rf} test block".encode()
    res = client.post(
        "/api/files/upload",
        files={"file": (f"rf_{rf}.txt", io.BytesIO(data), "text/plain")},
        data={"replication_factor": str(rf)},
    )
    assert res.status_code == 200
    obj = res.json()["object"]
    assert obj["replication_factor"] == rf
    assert len(obj["replicas"]) == rf
    distinct_nodes = {r["node_id"] for r in obj["replicas"]}
    assert len(distinct_nodes) == rf


def test_insufficient_healthy_nodes_raises_409(client):
    # Fail 3 out of 5 nodes so only 2 remain healthy
    node_manager.fail_node("node1", auto_repair=False)
    node_manager.fail_node("node2", auto_repair=False)
    node_manager.fail_node("node3", auto_repair=False)

    with pytest.raises(InsufficientNodesError):
        upload_service.upload_object(filename="too_many_replicas.bin", data=b"test", replication_factor=3)

    res = client.post(
        "/api/files/upload",
        files={"file": ("too_many.bin", io.BytesIO(b"12345"), "application/octet-stream")},
        data={"replication_factor": "3"},
    )
    assert res.status_code == 409
    assert res.json()["error"] == "INSUFFICIENT_HEALTHY_NODES"
