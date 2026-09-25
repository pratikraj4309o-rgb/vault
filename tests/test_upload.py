import io
import pytest
from backend.exceptions import InvalidConfigurationError
from backend.integrity.checksum import compute_sha256_bytes
from backend.services.upload_service import upload_service, sanitize_filename
from backend.storage.object_store import object_store


def test_upload_file_via_api_creates_metadata_and_replicas(client):
    content = b"NexStore VAULT test payload for SHA-256 verification"
    expected_sha = compute_sha256_bytes(content)

    res = client.post(
        "/api/files/upload",
        files={"file": ("telemetry.json", io.BytesIO(content), "application/json")},
        data={"replication_factor": "3"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "COMPLETED"

    obj = body["object"]
    assert obj["filename"] == "telemetry.json"
    assert obj["size"] == len(content)
    assert obj["checksum"] == expected_sha
    assert obj["version"] == 1
    assert obj["replication_factor"] == 3
    assert obj["status"] == "HEALTHY"
    assert len(obj["replicas"]) == 3

    for rep in obj["replicas"]:
        assert rep["checksum"] == expected_sha
        assert rep["status"] == "HEALTHY"
        disk_bytes = object_store.read_replica_bytes(rep["node_id"], obj["object_id"])
        assert disk_bytes == content


def test_upload_service_direct_and_version_increment():
    v1_bytes = b"version-1-payload"
    obj_v1 = upload_service.upload_object(filename="dataset.csv", data=v1_bytes, replication_factor=3)
    assert obj_v1["version"] == 1

    v2_bytes = b"version-2-updated-payload-longer"
    obj_v2 = upload_service.upload_object(
        filename="dataset.csv",
        data=v2_bytes,
        object_id=obj_v1["object_id"],
        replication_factor=3,
    )
    assert obj_v2["object_id"] == obj_v1["object_id"]
    assert obj_v2["version"] == 2
    assert obj_v2["checksum"] == compute_sha256_bytes(v2_bytes)


def test_invalid_filename_handling():
    with pytest.raises(InvalidConfigurationError):
        sanitize_filename("")

    with pytest.raises(InvalidConfigurationError):
        sanitize_filename("..")
