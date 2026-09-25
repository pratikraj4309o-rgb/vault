import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.config import settings
from backend.database import db
from backend.main import app
from backend.storage.node_manager import node_manager
from backend.storage.object_store import object_store


@pytest.fixture(autouse=True)
def isolated_vault_env(tmp_path: Path):
    """Isolate database and storage node directories per test."""
    test_db_path = tmp_path / "test_vault.db"
    test_storage_root = tmp_path / "storage_nodes"
    test_storage_root.mkdir(parents=True, exist_ok=True)

    db.set_db_path(test_db_path)
    object_store.set_storage_root(test_storage_root)

    settings.replication_factor = 3
    settings.node_count = 5

    saved_url = settings.supabase_url
    saved_key = settings.supabase_key
    saved_pass = settings.admin_password
    env_file = Path(__file__).resolve().parent.parent / ".env"
    saved_env_content = env_file.read_text(encoding="utf-8") if env_file.exists() else None

    db.initialize_schema()
    node_manager.initialize_nodes()
    yield

    settings.supabase_url = saved_url
    settings.supabase_key = saved_key
    settings.admin_password = saved_pass
    if saved_env_content is not None:
        env_file.write_text(saved_env_content, encoding="utf-8")


@pytest.fixture
def client():
    """Provide a FastAPI TestClient bound to the isolated test environment."""
    return TestClient(app)
