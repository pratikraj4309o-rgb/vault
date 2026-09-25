from fastapi import APIRouter
from backend.rebalancing.rebalancer import rebalancer

router = APIRouter(prefix="/api/rebalance", tags=["Rebalancing"])


@router.post("")
async def trigger_rebalance():
    return rebalancer.run_rebalance(force_balance=True)


@router.get("/status")
async def get_rebalance_status():
    return rebalancer.get_status()
