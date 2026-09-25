from typing import List, Set, Dict, Any
from backend.exceptions import InvalidConfigurationError, InsufficientNodesError
from backend.storage.node_manager import node_manager
from backend.storage.placement import placement_engine


def validate_and_select_nodes(
    replication_factor: int,
    object_size: int = 0,
    exclude_node_ids: Set[str] | None = None,
) -> List[Dict[str, Any]]:
    if replication_factor < 1:
        raise InvalidConfigurationError("Replication factor must be >= 1")

    healthy_nodes = node_manager.get_healthy_nodes()
    excluded = exclude_node_ids or set()
    available_healthy = [n for n in healthy_nodes if n["node_id"] not in excluded]

    if replication_factor > len(available_healthy):
        raise InsufficientNodesError(required=replication_factor, available=len(available_healthy))

    return placement_engine.select_nodes_for_object(
        required_count=replication_factor,
        object_size=object_size,
        exclude_node_ids=excluded,
    )
