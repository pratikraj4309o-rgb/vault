from fastapi import APIRouter, Query
from backend.database import db

router = APIRouter(prefix="/api/activity", tags=["Activity"])


@router.get("")
async def get_activity_logs(limit: int = Query(50, ge=1, le=500)):
    events = db.fetch_all(
        "SELECT * FROM activity_logs ORDER BY event_id DESC LIMIT ?", (limit,)
    )
    return {"events": events, "count": len(events)}
