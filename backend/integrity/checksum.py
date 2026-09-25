import hashlib
from pathlib import Path
from typing import Union

CHUNK_SIZE = 65536  # 64 KB chunks for memory-efficient large file hashing


def compute_sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    mv = memoryview(data)
    for offset in range(0, len(mv), CHUNK_SIZE):
        h.update(mv[offset : offset + CHUNK_SIZE])
    return h.hexdigest()


def compute_sha256_file(file_path: Union[str, Path]) -> str:
    path = Path(file_path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
