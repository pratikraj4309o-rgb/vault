from fastapi import APIRouter
from backend.replication.replica_manager import replica_manager

router = APIRouter(prefix="/api/replicas", tags=["Replicas"])


@router.get("")
async def list_all_replicas_endpoint():
    replicas = replica_manager.list_all_replicas()
    return {"replicas": replicas, "count": len(replicas)}
