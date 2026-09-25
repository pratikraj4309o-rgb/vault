from typing import Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel
from backend.storage.node_manager import node_manager

router = APIRouter(prefix="/api/nodes", tags=["Nodes"])


class ProvisionNodeRequest(BaseModel):
    node_id: Optional[str] = None
    reason: str = "Manual or policy-driven cluster auto-scaling"


@router.get("")
async def list_nodes():
    nodes = node_manager.get_all_nodes()
    return {"nodes": nodes, "count": len(nodes)}


@router.post("/provision")
async def provision_new_node(payload: Optional[ProvisionNodeRequest] = None):
    node_id = payload.node_id if payload else None
    reason = payload.reason if payload else "Dynamic cluster auto-scaling"
    node = node_manager.provision_node(node_id=node_id, reason=reason)
    return {"status": "provisioned", "node": node}


@router.get("/{node_id}")
async def get_node_details(node_id: str):
    return node_manager.get_node(node_id)


@router.delete("/{node_id}")
async def decommission_node_endpoint(node_id: str):
    return node_manager.decommission_node(node_id)


@router.post("/{node_id}/fail")
async def fail_node_endpoint(
    node_id: str,
    auto_repair: bool = Query(True),
    force_autoscale: bool = Query(False),
):
    return node_manager.fail_node(
        node_id,
        auto_repair=auto_repair,
        force_autoscale=force_autoscale,
    )


@router.post("/{node_id}/restore")
async def restore_node_endpoint(node_id: str):
    return node_manager.restore_node(node_id)


@router.post("/{node_id}/partition")
async def partition_node_endpoint(node_id: str):
    return node_manager.partition_node(node_id)


@router.post("/{node_id}/reconnect")
async def reconnect_node_endpoint(node_id: str):
    return node_manager.reconnect_node(node_id)
