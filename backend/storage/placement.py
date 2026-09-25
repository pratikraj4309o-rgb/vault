from typing import List, Set, Dict, Any
from backend.database import db
from backend.exceptions import InsufficientNodesError
from backend.storage.node_manager import node_manager


class PlacementEngine:
    """
    Placement engine that selects healthy, distinct storage nodes for object replicas.
    Considers:
    1. Node health (status == ONLINE and network_status == CONNECTED)
    2. Exclusion of nodes that already hold a valid replica of the object
    3. Available storage capacity
    4. Storage utilization balance (lowest utilization ratio first, then node_id)
    """

    def select_nodes_for_object(
        self,
        required_count: int,
        object_size: int = 0,
        exclude_node_ids: Set[str] | None = None,
    ) -> List[Dict[str, Any]]:
        if required_count < 1:
            return []

        excluded = exclude_node_ids or set()
        healthy_nodes = node_manager.get_healthy_nodes()

        candidates = []
        for n in healthy_nodes:
            if n["node_id"] in excluded:
                continue
            free_space = n["capacity"] - n["used_capacity"]
            if free_space >= object_size:
                util_ratio = n["used_capacity"] / max(1, n["capacity"])
                candidates.append((util_ratio, n["node_id"], n))

        if len(candidates) < required_count:
            raise InsufficientNodesError(required=required_count, available=len(candidates))

        # Sort by lowest utilization ratio first, breaking ties deterministically by node_id (node1, node2, node3...)
        candidates.sort(key=lambda item: (round(item[0], 4), item[1]))
        return [item[2] for item in candidates[:required_count]]


placement_engine = PlacementEngine()
