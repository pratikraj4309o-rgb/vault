from fastapi import APIRouter
from backend.services.object_service import object_service

router = APIRouter(prefix="/api/integrity", tags=["Integrity"])


@router.post("/scan")
async def trigger_integrity_scan():
    return object_service.scan_cluster_integrity()
