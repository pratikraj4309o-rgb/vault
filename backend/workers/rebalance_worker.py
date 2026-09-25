import asyncio
from backend.config import settings
from backend.logging_config import logger
from backend.rebalancing.rebalancer import rebalancer


async def start_rebalance_worker(stop_event: asyncio.Event) -> None:
    logger.info("Background RebalanceWorker started (threshold=%d%%)", settings.rebalance_threshold)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            try:
                await asyncio.to_thread(rebalancer.run_rebalance, False)
            except Exception as exc:
                logger.error("RebalanceWorker error: %s", exc)
