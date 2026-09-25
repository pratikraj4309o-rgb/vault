import io
from backend.integrity.checksum import compute_sha256_file
from backend.storage.object_store import object_store


def test_corrupt_replica_endpoint_injects_bitrot_and_detects_checksum_mismatch(client):
    original = b"Immutable financial ledger block #4096"
    up = client.post(
        "/api/files/upload",
        files={"file": ("block_4096.dat", io.BytesIO(original), "application/octet-stream")},
        data={"replication_factor": "3"},
    ).json()["object"]
    obj_id = up["object_id"]
    target_node = up["replicas"][0]["node_id"]

    corrupt_res = client.post(
        f"/api/files/{obj_id}/corrupt",
        json={"node_id": target_node, "auto_repair": False},
    )
    assert corrupt_res.status_code == 200
    body = corrupt_res.json()
    assert body["status"] == "CORRUPTED"
    assert body["corrupted_node_id"] == target_node

    # Physical bytes on disk must differ from original SHA-256
    corrupted_path = object_store.get_replica_path(target_node, obj_id)
    assert compute_sha256_file(corrupted_path) != up["checksum"]

    # Verification report inside response flags CHECKSUM_MISMATCH
    ver = body["verification"]
    assert ver["integrity"] == "CHECKSUM_MISMATCH"
    assert ver["corrupted_replicas"] == 1
    mismatched = [r for r in ver["replicas"] if r["node_id"] == target_node][0]
    assert mismatched["status"] == "CHECKSUM_MISMATCH"
    assert mismatched["verified"] is False

    # Downloading the file still succeeds by failing over to a healthy replica
    dl = client.get(f"/api/files/{obj_id}")
    assert dl.status_code == 200
    assert dl.content == original
