from typing import List, Dict, Any
from backend.config import settings
from backend.database import db
from backend.health.heartbeat import heartbeat_manager
from backend.logging_config import logger
from backend.storage.node_manager import node_manager


class FailureDetector:
    """Detects nodes whose heartbeat has exceeded the configured timeout."""

    def check_timeouts(self) -> List[Dict[str, Any]]:
        nodes = db.fetch_all("SELECT * FROM nodes WHERE status = 'ONLINE'")
        failed_detected = []
        for n in nodes:
            elapsed = heartbeat_manager.seconds_since(n["last_heartbeat"])
            if elapsed > settings.heartbeat_timeout:
                logger.warning(
                    "Node %s heartbeat timeout (%.1fs > %ds) -> marking FAILED",
                    n["node_id"],
                    elapsed,
                    settings.heartbeat_timeout,
                )
                res = node_manager.fail_node(n["node_id"], auto_repair=True)
                failed_detected.append(res)
        return failed_detected


failure_detector = FailureDetector()
