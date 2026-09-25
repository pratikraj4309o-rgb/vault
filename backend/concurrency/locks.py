import threading
from contextlib import contextmanager
from typing import Dict, Iterator


class ReadWriteLock:
    """Fine-grained Read-Write Lock allowing multiple concurrent readers or a single exclusive writer."""

    def __init__(self) -> None:
        self._read_ready = threading.Condition(threading.RLock())
        self._readers = 0
        self._writers = 0
        self._write_waiters = 0

    @contextmanager
    def read_lock(self) -> Iterator[None]:
        with self._read_ready:
            while self._writers > 0 or self._write_waiters > 0:
                self._read_ready.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._read_ready:
                self._readers -= 1
                if self._readers == 0:
                    self._read_ready.notify_all()

    @contextmanager
    def write_lock(self) -> Iterator[None]:
        with self._read_ready:
            self._write_waiters += 1
            try:
                while self._readers > 0 or self._writers > 0:
                    self._read_ready.wait()
                self._writers += 1
            finally:
                self._write_waiters -= 1
        try:
            yield
        finally:
            with self._read_ready:
                self._writers -= 1
                self._read_ready.notify_all()


class ObjectLockManager:
    """Manages per-object ReadWriteLocks so reads/writes to different objects never block each other."""

    def __init__(self) -> None:
        self._global_lock = threading.Lock()
        self._locks: Dict[str, ReadWriteLock] = {}

    def _get_lock(self, key: str) -> ReadWriteLock:
        with self._global_lock:
            if key not in self._locks:
                self._locks[key] = ReadWriteLock()
            return self._locks[key]

    @contextmanager
    def acquire_read(self, key: str) -> Iterator[None]:
        lock = self._get_lock(key)
        with lock.read_lock():
            yield

    @contextmanager
    def acquire_write(self, key: str) -> Iterator[None]:
        lock = self._get_lock(key)
        with lock.write_lock():
            yield


lock_manager = ObjectLockManager()
