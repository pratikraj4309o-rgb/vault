from typing import Dict, Any
from backend.health.failure_detector import failure_detector
from backend.health.heartbeat import heartbeat_manager
from backend.storage.node_manager import node_manager


class HealthChecker:
    """Performs periodic health checks and returns cluster health summary."""

    def run_health_cycle(self) -> Dict[str, Any]:
        # Check if any node timed out prior to pulsing active connected nodes
        timed_out = failure_detector.check_timeouts()
        heartbeat_manager.pulse_online_nodes()
        node_manager.refresh_all_node_metrics()
        return self.get_health_summary(timed_out_count=len(timed_out))

    def get_health_summary(self, timed_out_count: int = 0) -> Dict[str, Any]:
        nodes = node_manager.get_all_nodes()
        total = len(nodes)
        healthy = sum(1 for n in nodes if n["status"] == "ONLINE")
        failed = sum(1 for n in nodes if n["status"] == "FAILED")
        partitioned = sum(1 for n in nodes if n["status"] == "PARTITIONED")

        if failed == 0 and partitioned == 0 and healthy == total:
            status = "healthy"
        elif healthy > 0:
            status = "degraded"
        else:
            status = "critical"

        return {
            "status": status,
            "nodes": total,
            "healthy_nodes": healthy,
            "failed_nodes": failed,
            "partitioned_nodes": partitioned,
            "timed_out_detected": timed_out_count,
        }


health_checker = HealthChecker()
