import io
from concurrent.futures import ThreadPoolExecutor
import pytest
from backend.exceptions import VersionConflictError
from backend.services.download_service import download_service
from backend.services.upload_service import upload_service


def test_optimistic_concurrency_expected_version_conflict(client):
    obj = upload_service.upload_object(filename="state.json", data=b'{"step": 1}', replication_factor=3)
    obj_id = obj["object_id"]
    assert obj["version"] == 1

    # Valid update with expected_version=1 succeeds -> version becomes 2
    obj_v2 = upload_service.upload_object(
        filename="state.json",
        data=b'{"step": 2}',
        object_id=obj_id,
        expected_version=1,
    )
    assert obj_v2["version"] == 2

    # Stale update still passing expected_version=1 must raise VersionConflictError (409)
    with pytest.raises(VersionConflictError):
        upload_service.upload_object(
            filename="state.json",
            data=b'{"step": "conflict"}',
            object_id=obj_id,
            expected_version=1,
        )

    api_res = client.post(
        "/api/files/upload",
        files={"file": ("state.json", io.BytesIO(b'{"step": 99}'), "application/json")},
        data={"object_id": obj_id, "expected_version": "1"},
    )
    assert api_res.status_code == 409
    assert api_res.json()["error"] == "VERSION_CONFLICT"


def test_concurrent_reads_and_writes_safety():
    base = upload_service.upload_object(filename="shared.bin", data=b"initial-data", replication_factor=3)
    obj_id = base["object_id"]

    def writer(idx: int):
        return upload_service.upload_object(
            filename=f"concurrent_{idx}.bin",
            data=f"payload-{idx}".encode(),
            replication_factor=3,
        )

    def reader():
        _, _, data = download_service.retrieve_object(obj_id)
        return data

    with ThreadPoolExecutor(max_workers=6) as pool:
        write_futures = [pool.submit(writer, i) for i in range(5)]
        read_futures = [pool.submit(reader) for _ in range(5)]

        for wf in write_futures:
            res = wf.result()
            assert res["status"] == "HEALTHY"
            assert len(res["replicas"]) == 3

        for rf in read_futures:
            assert rf.result() == b"initial-data"
