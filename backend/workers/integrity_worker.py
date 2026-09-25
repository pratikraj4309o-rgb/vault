import asyncio
from backend.config import settings
from backend.logging_config import logger
from backend.services.object_service import object_service


async def start_integrity_worker(stop_event: asyncio.Event) -> None:
    logger.info("Background IntegrityWorker started (interval=%ds)", settings.integrity_check_interval)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(5, settings.integrity_check_interval))
        except asyncio.TimeoutError:
            try:
                await asyncio.to_thread(object_service.scan_cluster_integrity)
            except Exception as exc:
                logger.error("IntegrityWorker error: %s", exc)
