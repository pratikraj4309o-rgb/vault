import os
from pathlib import Path
from typing import Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv(BASE_DIR / ".env")


class Settings:
    def __init__(self) -> None:
        self.app_name: str = os.getenv("APP_NAME", "NexStore VAULT")
        self.host: str = os.getenv("HOST", "127.0.0.1")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.replication_factor: int = int(os.getenv("REPLICATION_FACTOR", "3"))
        self.health_check_interval: int = int(os.getenv("HEALTH_CHECK_INTERVAL", "5"))
        self.heartbeat_timeout: int = int(os.getenv("HEARTBEAT_TIMEOUT", "15"))
        self.repair_interval: int = int(os.getenv("REPAIR_INTERVAL", "3"))
        self.integrity_check_interval: int = int(os.getenv("INTEGRITY_CHECK_INTERVAL", "30"))
        self.rebalance_threshold: int = int(os.getenv("REBALANCE_THRESHOLD", "80"))
        self.max_storage_per_node: int = int(os.getenv("MAX_STORAGE_PER_NODE", str(10 * 1024 * 1024 * 1024)))
        self.node_count: int = int(os.getenv("NODE_COUNT", "5"))
        self.auto_scale_enabled: bool = os.getenv("AUTO_SCALE_ENABLED", "true").lower() in ("true", "1", "yes")
        self.max_auto_scale_nodes: int = int(os.getenv("MAX_AUTO_SCALE_NODES", "12"))

        self.supabase_url: str = os.getenv("SUPABASE_URL", "")
        self.supabase_key: str = os.getenv("SUPABASE_KEY", "")
        self.admin_password: str = os.getenv("ADMIN_PASSWORD", "admin123")

        is_vercel = os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV") is not None
        if is_vercel:
            tmp_root = Path("/tmp/vault")
            self.database_path: Path = tmp_root / "data" / "vault.db"
            self.storage_root: Path = tmp_root / "storage_nodes"
        else:
            db_rel = os.getenv("DATABASE_PATH", "data/vault.db")
            self.database_path: Path = (BASE_DIR / db_rel).resolve()
            storage_rel = os.getenv("STORAGE_ROOT", "storage_nodes")
            self.storage_root: Path = (BASE_DIR / storage_rel).resolve()

    def update_admin_password(self, new_pass: str) -> None:
        self.admin_password = new_pass
        os.environ["ADMIN_PASSWORD"] = new_pass
        env_path = BASE_DIR / ".env"
        lines = []
        if env_path.exists():
            try:
                lines = env_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return
        new_lines = []
        found = False
        for line in lines:
            if line.strip().startswith("ADMIN_PASSWORD="):
                new_lines.append(f"ADMIN_PASSWORD={new_pass}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"ADMIN_PASSWORD={new_pass}")
        try:
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except OSError:
            pass

    def update_supabase_credentials(self, url: str, key: str) -> None:
        self.supabase_url = url
        self.supabase_key = key
        os.environ["SUPABASE_URL"] = url
        os.environ["SUPABASE_KEY"] = key

        # Update or append to .env
        env_path = BASE_DIR / ".env"
        lines = []
        if env_path.exists():
            try:
                lines = env_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return

        new_lines = []
        found_url = False
        found_key = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("SUPABASE_URL="):
                new_lines.append(f"SUPABASE_URL={url}")
                found_url = True
            elif stripped.startswith("SUPABASE_KEY="):
                new_lines.append(f"SUPABASE_KEY={key}")
                found_key = True
            else:
                new_lines.append(line)

        if not found_url:
            new_lines.append(f"SUPABASE_URL={url}")
        if not found_key:
            new_lines.append(f"SUPABASE_KEY={key}")

        try:
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except OSError:
            pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_name": self.app_name,
            "host": self.host,
            "port": self.port,
            "replication_factor": self.replication_factor,
            "health_check_interval": self.health_check_interval,
            "heartbeat_timeout": self.heartbeat_timeout,
            "repair_interval": self.repair_interval,
            "integrity_check_interval": self.integrity_check_interval,
            "rebalance_threshold": self.rebalance_threshold,
            "max_storage_per_node": self.max_storage_per_node,
            "node_count": self.node_count,
            "auto_scale_enabled": self.auto_scale_enabled,
            "max_auto_scale_nodes": self.max_auto_scale_nodes,
            "supabase_configured": bool(self.supabase_url and self.supabase_key),
            "supabase_url": self.supabase_url,
            "admin_configured": bool(self.admin_password),
        }


settings = Settings()
