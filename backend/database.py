import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Any, List, Dict

from backend.config import settings
from backend.logging_config import logger


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DatabaseManager:
    """Thread-safe SQLite database abstraction with WAL mode and schema auto-initialization."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path or settings.database_path
        self._lock = threading.RLock()
        self._schema_initialized: bool = False

    @property
    def db_path(self) -> Path:
        return self._db_path

    def set_db_path(self, new_path: Path) -> None:
        with self._lock:
            self._db_path = new_path
            self._schema_initialized = False

    def get_connection(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.OperationalError:
            conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA synchronous=NORMAL;")

        if not self._schema_initialized:
            try:
                row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nodes' LIMIT 1;").fetchone()
                if not row:
                    self._create_tables(conn)
                self._schema_initialized = True
            except Exception as e:
                logger.warning("Could not auto-verify schema on connect: %s", e)

        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self.get_connection()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    @contextmanager
    def read_conn(self) -> Iterator[sqlite3.Connection]:
        conn = self.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'ONLINE',
                    capacity INTEGER NOT NULL,
                    used_capacity INTEGER NOT NULL DEFAULT 0,
                    object_count INTEGER NOT NULL DEFAULT 0,
                    last_heartbeat TEXT NOT NULL,
                    network_status TEXT NOT NULL DEFAULT 'CONNECTED',
                    health_status TEXT NOT NULL DEFAULT 'HEALTHY'
                );

                CREATE TABLE IF NOT EXISTS objects (
                    object_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    content_type TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    replication_factor INTEGER NOT NULL DEFAULT 3,
                    status TEXT NOT NULL DEFAULT 'HEALTHY'
                );

                CREATE TABLE IF NOT EXISTS replicas (
                    replica_id TEXT PRIMARY KEY,
                    object_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'HEALTHY',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (object_id) REFERENCES objects(object_id) ON DELETE CASCADE,
                    FOREIGN KEY (node_id) REFERENCES nodes(node_id)
                );

                CREATE INDEX IF NOT EXISTS idx_replicas_object_id ON replicas(object_id);
                CREATE INDEX IF NOT EXISTS idx_replicas_node_id ON replicas(node_id);

                CREATE TABLE IF NOT EXISTS repair_jobs (
                    repair_id TEXT PRIMARY KEY,
                    object_id TEXT NOT NULL,
                    source_node_id TEXT,
                    failed_node_id TEXT,
                    target_node_id TEXT,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'QUEUED',
                    progress INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_ms INTEGER,
                    error_message TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_repair_jobs_object_id ON repair_jobs(object_id);
                CREATE INDEX IF NOT EXISTS idx_repair_jobs_status ON repair_jobs(status);

                CREATE TABLE IF NOT EXISTS activity_logs (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    object_id TEXT,
                    node_id TEXT,
                    severity TEXT NOT NULL DEFAULT 'INFO',
                    details TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS system_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT NOT NULL,
                    payload TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def initialize_schema(self) -> None:
        with self.transaction() as conn:
            self._create_tables(conn)
        self._schema_initialized = True
        logger.info("Database schema initialized at %s", self._db_path)

    def log_activity(
        self,
        event_type: str,
        message: str,
        object_id: Optional[str] = None,
        node_id: Optional[str] = None,
        severity: str = "INFO",
        details: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        now = utc_now_iso()
        sql = """
            INSERT INTO activity_logs (event_type, message, object_id, node_id, severity, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        if conn is not None:
            conn.execute(sql, (event_type, message, object_id, node_id, severity, details, now))
        else:
            with self.transaction() as c:
                c.execute(sql, (event_type, message, object_id, node_id, severity, details, now))

    def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self.read_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        with self.read_conn() as conn:
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None


db = DatabaseManager()
