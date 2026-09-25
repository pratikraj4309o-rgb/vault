import threading
from typing import Dict, Any


class RequestManager:
    """Tracks active concurrent read/write requests for observability and safe coordination."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_reads: int = 0
        self._active_writes: int = 0
        self._total_reads: int = 0
        self._total_writes: int = 0

    def begin_read(self) -> None:
        with self._lock:
            self._active_reads += 1
            self._total_reads += 1

    def end_read(self) -> None:
        with self._lock:
            self._active_reads = max(0, self._active_reads - 1)

    def begin_write(self) -> None:
        with self._lock:
            self._active_writes += 1
            self._total_writes += 1

    def end_write(self) -> None:
        with self._lock:
            self._active_writes = max(0, self._active_writes - 1)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_reads": self._active_reads,
                "active_writes": self._active_writes,
                "total_reads": self._total_reads,
                "total_writes": self._total_writes,
            }


request_manager = RequestManager()
