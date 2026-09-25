from typing import List, Dict, Any
from backend.repair.repair_manager import repair_manager


def run_repair_cycle() -> List[Dict[str, Any]]:
    return repair_manager.process_pending_repairs()
