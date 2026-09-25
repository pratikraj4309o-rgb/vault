from fastapi import APIRouter
from backend.health.health_checker import health_checker

router = APIRouter(prefix="/api/health", tags=["Health"])


@router.get("")
async def get_health():
    return health_checker.get_health_summary()
