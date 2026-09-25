import asyncio
from backend.config import settings
from backend.health.health_checker import health_checker
from backend.logging_config import logger


async def start_health_worker(stop_event: asyncio.Event) -> None:
    logger.info("Background HealthWorker started (interval=%ds)", settings.health_check_interval)
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(health_checker.run_health_cycle)
        except Exception as exc:
            logger.error("HealthWorker error: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(1, settings.health_check_interval))
        except asyncio.TimeoutError:
            pass
