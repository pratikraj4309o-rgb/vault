import hashlib
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Response, Query, Header
from backend.config import settings
from backend.schemas import CorruptReplicaRequest
from backend.services.delete_service import delete_service
from backend.services.download_service import download_service
from backend.services.object_service import object_service
from backend.services.upload_service import upload_service

router = APIRouter(prefix="/api/files", tags=["Files"])


@router.get("")
async def list_files(authorization: Optional[str] = Header(None)):
    is_admin = False
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        expected_admin = hashlib.sha256(f"admin-{settings.admin_password}".encode()).hexdigest()
        if token == expected_admin:
            is_admin = True

    if not is_admin:
        return {
            "files": [],
            "count": 0,
            "restricted": True,
            "message": "File repository is protected. Admin authentication required to view files.",
        }

    objects = object_service.list_objects()
    return {"files": objects, "count": len(objects), "restricted": False, "is_admin": True}


@router.post("/upload")
async def upload_file_endpoint(
    file: UploadFile = File(...),
    replication_factor: Optional[int] = Form(None),
    object_id: Optional[str] = Form(None),
    expected_version: Optional[int] = Form(None),
):
    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    obj = upload_service.upload_object(
        filename=file.filename or "unnamed.bin",
        data=data,
        content_type=content_type,
        replication_factor=replication_factor,
        object_id=object_id,
        expected_version=expected_version,
    )
    return {
        "status": "COMPLETED",
        "object": obj,
        "pipeline": {
            "uploading": "COMPLETED",
            "hashing": "COMPLETED",
            "replicating": "COMPLETED",
            "verifying": "COMPLETED",
        },
    }


@router.get("/{object_id}")
async def download_file_endpoint(object_id: str, metadata_only: bool = Query(False)):
    if metadata_only:
        return object_service.get_object(object_id)

    obj, served_node, data = download_service.retrieve_object(object_id)
    headers = {
        "Content-Disposition": f'attachment; filename="{obj["filename"]}"',
        "X-Vault-Object-Id": obj["object_id"],
        "X-Vault-Served-Node": served_node,
        "X-Vault-Checksum": obj["checksum"],
        "X-Vault-Version": str(obj["version"]),
    }
    return Response(content=data, media_type=obj["content_type"], headers=headers)


@router.get("/{object_id}/metadata")
async def get_file_metadata_endpoint(object_id: str):
    return object_service.get_object(object_id)


@router.delete("/{object_id}")
async def delete_file_endpoint(object_id: str):
    return delete_service.delete_object(object_id)


@router.get("/{object_id}/replicas")
async def get_file_replicas_endpoint(object_id: str):
    obj = object_service.get_object(object_id)
    return {
        "object_id": obj["object_id"],
        "filename": obj["filename"],
        "version": obj["version"],
        "expected_checksum": obj["checksum"],
        "replication_factor": obj["replication_factor"],
        "current_replicas": obj["current_replicas"],
        "healthy_replicas": obj["healthy_replicas"],
        "missing_replicas": obj["missing_replicas"],
        "replicas": obj["replicas"],
    }


@router.post("/{object_id}/verify")
async def verify_file_endpoint(object_id: str, queue_repair: bool = Query(True)):
    return object_service.verify_object(object_id, queue_repair=queue_repair)


@router.post("/{object_id}/corrupt")
async def corrupt_file_replica_endpoint(
    object_id: str,
    payload: Optional[CorruptReplicaRequest] = None,
):
    node_id = payload.node_id if payload else None
    replica_id = payload.replica_id if payload else None
    auto_repair = payload.auto_repair if payload else False
    return object_service.corrupt_replica(
        object_id=object_id,
        node_id=node_id,
        replica_id=replica_id,
        auto_repair=auto_repair,
    )
