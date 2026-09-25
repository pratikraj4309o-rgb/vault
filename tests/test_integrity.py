import io
from backend.storage.object_store import object_store


def test_verify_endpoint_and_full_cluster_integrity_scan(client):
    data1 = b"Integrity scan file alpha"
    data2 = b"Integrity scan file beta"

    obj1 = client.post(
        "/api/files/upload",
        files={"file": ("alpha.txt", io.BytesIO(data1), "text/plain")},
    ).json()["object"]
    obj2 = client.post(
        "/api/files/upload",
        files={"file": ("beta.txt", io.BytesIO(data2), "text/plain")},
    ).json()["object"]

    # Verify single healthy object
    v1 = client.post(f"/api/files/{obj1['object_id']}/verify")
    assert v1.status_code == 200
    assert v1.json()["integrity"] == "VERIFIED"
    assert v1.json()["healthy_replicas"] == 3
    assert v1.json()["corrupted_replicas"] == 0

    # Inject corruption on one replica of obj2
    bad_node = obj2["replicas"][0]["node_id"]
    object_store.get_replica_path(bad_node, obj2["object_id"]).write_bytes(b"BITROT_CORRUPTION")

    # Run cluster-wide integrity scan
    scan = client.post("/api/integrity/scan")
    assert scan.status_code == 200
    scan_body = scan.json()
    assert scan_body["scanned_objects"] == 2
    assert scan_body["corrupted_replicas_detected"] == 1
