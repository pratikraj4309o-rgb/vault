import asyncio
from backend.config import settings
from backend.logging_config import logger
from backend.repair.repair_manager import repair_manager


async def start_repair_worker(stop_event: asyncio.Event) -> None:
    logger.info("Background RepairWorker started (interval=%ds)", settings.repair_interval)
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(repair_manager.process_pending_repairs)
        except Exception as exc:
            logger.error("RepairWorker error: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(1, settings.repair_interval))
        except asyncio.TimeoutError:
            pass
