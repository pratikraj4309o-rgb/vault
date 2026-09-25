from datetime import datetime, timezone
from backend.database import db, utc_now_iso


class HeartbeatManager:
    """Updates and reads node heartbeats."""

    def record_heartbeat(self, node_id: str) -> str:
        now = utc_now_iso()
        with db.transaction() as conn:
            conn.execute(
                "UPDATE nodes SET last_heartbeat = ? WHERE node_id = ? AND status = 'ONLINE'",
                (now, node_id),
            )
        return now

    def pulse_online_nodes(self) -> None:
        now = utc_now_iso()
        with db.transaction() as conn:
            conn.execute(
                "UPDATE nodes SET last_heartbeat = ? WHERE status = 'ONLINE' AND network_status = 'CONNECTED'",
                (now,),
            )

    @staticmethod
    def seconds_since(iso_timestamp: str) -> float:
        try:
            dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - dt).total_seconds()
        except Exception:
            return 0.0


heartbeat_manager = HeartbeatManager()
