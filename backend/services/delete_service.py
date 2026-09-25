from typing import Dict, Any
from backend.concurrency.locks import lock_manager
from backend.database import db
from backend.exceptions import ObjectNotFoundError
from backend.logging_config import logger
from backend.models import EventType
from backend.storage.node_manager import node_manager
from backend.storage.object_store import object_store
from backend.supabase_manager import supabase_manager


class DeleteService:
    """Safely deletes an object, its physical replica files across all nodes, and its metadata."""

    def delete_object(self, object_id: str) -> Dict[str, Any]:
        with lock_manager.acquire_write(object_id):
            obj = db.fetch_one("SELECT * FROM objects WHERE object_id = ?", (object_id,))
            if not obj:
                raise ObjectNotFoundError(object_id)

            replicas = db.fetch_all("SELECT * FROM replicas WHERE object_id = ?", (object_id,))
            deleted_nodes = []

            for rep in replicas:
                node_id = rep["node_id"]
                try:
                    object_store.delete_replica(node_id, object_id)
                    deleted_nodes.append(node_id)
                except Exception as exc:
                    logger.warning("Partial failure deleting replica on %s: %s", node_id, exc)

            with db.transaction() as conn:
                conn.execute("DELETE FROM replicas WHERE object_id = ?", (object_id,))
                conn.execute("DELETE FROM repair_jobs WHERE object_id = ?", (object_id,))
                conn.execute("DELETE FROM objects WHERE object_id = ?", (object_id,))
                for n_id in deleted_nodes:
                    db.log_activity(
                        EventType.REPLICA_DELETED.value,
                        f"Deleted replica of {obj['filename']} from {n_id.upper()}",
                        object_id=object_id,
                        node_id=n_id,
                        severity="INFO",
                        conn=conn,
                    )
                db.log_activity(
                    EventType.OBJECT_DELETED.value,
                    f"Object deleted: {obj['filename']} ({len(deleted_nodes)} replica(s) removed)",
                    object_id=object_id,
                    severity="INFO",
                    conn=conn,
                )

            node_manager.refresh_all_node_metrics()

            # Sync to Supabase in background if connected
            supabase_manager.async_delete_object(object_id)
            supabase_manager.async_delete_file_storage(object_id, obj["filename"])
            for n_id in deleted_nodes:
                supabase_manager.async_sync_node(n_id)

            return {
                "deleted": True,
                "object_id": object_id,
                "filename": obj["filename"],
                "replicas_removed": len(deleted_nodes),
                "nodes": deleted_nodes,
            }


delete_service = DeleteService()
