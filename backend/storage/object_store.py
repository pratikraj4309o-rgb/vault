import re
import shutil
from pathlib import Path
from typing import Iterator, Optional
from backend.config import settings
from backend.exceptions import InvalidConfigurationError
from backend.integrity.checksum import compute_sha256_file, CHUNK_SIZE

SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def sanitize_identifier(value: str, label: str = "identifier") -> str:
    if not value or not SAFE_ID_RE.match(value) or ".." in value:
        raise InvalidConfigurationError(f"Invalid {label}: '{value}'")
    return value


class ObjectStore:
    """Manages physical object storage across independent node directories."""

    def __init__(self, storage_root: Optional[Path] = None) -> None:
        self._storage_root = storage_root or settings.storage_root

    @property
    def storage_root(self) -> Path:
        return self._storage_root

    def set_storage_root(self, path: Path) -> None:
        self._storage_root = path.resolve()

    def get_node_dir(self, node_id: str) -> Path:
        safe_node = sanitize_identifier(node_id, "node_id")
        node_dir = (self._storage_root / safe_node).resolve()
        if not str(node_dir).startswith(str(self._storage_root.resolve())):
            raise InvalidConfigurationError("Path traversal detected in node_id")
        return node_dir

    def get_node_data_dir(self, node_id: str) -> Path:
        data_dir = self.get_node_dir(node_id) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def get_replica_path(self, node_id: str, object_id: str) -> Path:
        safe_obj = sanitize_identifier(object_id, "object_id")
        data_dir = self.get_node_data_dir(node_id)
        target = (data_dir / safe_obj).resolve()
        if not str(target).startswith(str(data_dir.resolve())):
            raise InvalidConfigurationError("Path traversal detected in object_id")
        return target

    def write_replica_bytes(self, node_id: str, object_id: str, data: bytes) -> str:
        """Atomically writes object bytes to a node's data directory and returns SHA-256 checksum."""
        target_path = self.get_replica_path(node_id, object_id)
        tmp_path = target_path.with_suffix(".tmp")
        with tmp_path.open("wb") as f:
            mv = memoryview(data)
            for offset in range(0, len(mv), CHUNK_SIZE):
                f.write(mv[offset : offset + CHUNK_SIZE])
        tmp_path.replace(target_path)
        return compute_sha256_file(target_path)

    def copy_replica_between_nodes(self, source_node_id: str, target_node_id: str, object_id: str) -> str:
        """Copies a physical replica from source_node to target_node atomically and verifies SHA-256."""
        src_path = self.get_replica_path(source_node_id, object_id)
        if not src_path.exists():
            raise FileNotFoundError(f"Source replica missing on {source_node_id} for {object_id}")

        dst_path = self.get_replica_path(target_node_id, object_id)
        tmp_dst = dst_path.with_suffix(".repair.tmp")
        shutil.copy2(src_path, tmp_dst)
        tmp_dst.replace(dst_path)
        return compute_sha256_file(dst_path)

    def read_replica_bytes(self, node_id: str, object_id: str) -> bytes:
        path = self.get_replica_path(node_id, object_id)
        if not path.exists():
            raise FileNotFoundError(f"Replica file not found on {node_id} for {object_id}")
        return path.read_bytes()

    def stream_replica(self, node_id: str, object_id: str) -> Iterator[bytes]:
        path = self.get_replica_path(node_id, object_id)
        with path.open("rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    def delete_replica(self, node_id: str, object_id: str) -> bool:
        path = self.get_replica_path(node_id, object_id)
        if path.exists():
            path.unlink()
            return True
        return False


object_store = ObjectStore()
