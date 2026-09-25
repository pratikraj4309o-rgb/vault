from fastapi import APIRouter
from backend.repair.repair_manager import repair_manager
from backend.repair.repair_queue import repair_queue

router = APIRouter(prefix="/api/repairs", tags=["Repairs"])


@router.get("")
async def list_repair_jobs():
    jobs = repair_queue.list_all_jobs()
    return {"repairs": jobs, "count": len(jobs)}


@router.post("/run")
async def run_pending_repairs_endpoint():
    processed = repair_manager.process_pending_repairs()
    return {"processed": len(processed), "jobs": processed}


@router.post("/{repair_id}/retry")
async def retry_repair_endpoint(repair_id: str):
    job = repair_manager.retry_repair(repair_id)
    return {"status": "retried", "repair": job}
