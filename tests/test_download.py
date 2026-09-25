import io
from backend.integrity.checksum import compute_sha256_bytes
from backend.storage.object_store import object_store


def test_download_returns_verified_content_and_headers(client):
    raw_data = b"Binary firmware image v4.2.0 for satellite cluster"
    expected_sha = compute_sha256_bytes(raw_data)

    up = client.post(
        "/api/files/upload",
        files={"file": ("firmware.bin", io.BytesIO(raw_data), "application/octet-stream")},
    ).json()["object"]

    dl = client.get(f"/api/files/{up['object_id']}")
    assert dl.status_code == 200
    assert dl.content == raw_data
    assert dl.headers["X-Vault-Object-Id"] == up["object_id"]
    assert dl.headers["X-Vault-Checksum"] == expected_sha
    assert dl.headers["X-Vault-Version"] == "1"
    assert dl.headers["X-Vault-Served-Node"] in {"node1", "node2", "node3", "node4", "node5"}


def test_download_missing_object_returns_404(client):
    res = client.get("/api/files/obj_nonexistent_999")
    assert res.status_code == 404
    assert res.json()["error"] == "OBJECT_NOT_FOUND"


def test_download_failover_when_primary_replica_is_corrupted(client):
    raw_data = b"Critical ledger record that must never be served corrupted"
    up = client.post(
        "/api/files/upload",
        files={"file": ("ledger.dat", io.BytesIO(raw_data), "application/octet-stream")},
        data={"replication_factor": "3"},
    ).json()["object"]
    object_id = up["object_id"]
    first_node = sorted(r["node_id"] for r in up["replicas"])[0]

    # Tamper with the first node's physical file directly on disk
    replica_path = object_store.get_replica_path(first_node, object_id)
    replica_path.write_bytes(b"TAMPERED_UNVERIFIED_DISK_BYTES")

    # Download must detect mismatch on first_node, mark it CORRUPTED, and transparently serve from a healthy replica
    dl = client.get(f"/api/files/{object_id}")
    assert dl.status_code == 200
    assert dl.content == raw_data
    assert dl.headers["X-Vault-Served-Node"] != first_node
