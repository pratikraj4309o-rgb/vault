import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import (
    activity,
    files,
    health,
    integrity,
    nodes,
    rebalance,
    repair,
    replicas,
    system,
    supabase_router,
    auth,
)
from backend.config import settings, BASE_DIR
from backend.database import db
from backend.exceptions import VaultException
from backend.logging_config import logger
from backend.storage.node_manager import node_manager
from backend.workers.health_worker import start_health_worker
from backend.workers.integrity_worker import start_integrity_worker
from backend.workers.rebalance_worker import start_rebalance_worker
from backend.workers.repair_worker import start_repair_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize SQLite schema & 5 simulated storage nodes
    db.initialize_schema()
    node_manager.initialize_nodes()

    # 2. Start background workers
    stop_event = asyncio.Event()
    tasks = [
        asyncio.create_task(start_health_worker(stop_event)),
        asyncio.create_task(start_repair_worker(stop_event)),
        asyncio.create_task(start_integrity_worker(stop_event)),
        asyncio.create_task(start_rebalance_worker(stop_event)),
    ]
    logger.info("%s initialized and ready on http://%s:%d", settings.app_name, settings.host, settings.port)
    try:
        yield
    finally:
        stop_event.set()
        for t in tasks:
            t.cancel()


app = FastAPI(
    title="NexStore VAULT — Distributed Object Storage System",
    version="1.0.0",
    description="Fault-tolerant distributed object storage engine with configurable replication, SHA-256 verification, automatic self-healing repair, and rebalancing.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(VaultException)
async def vault_exception_handler(request: Request, exc: VaultException):
    logger.warning("VaultException [%s]: %s", exc.error_code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "detail": exc.message,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled internal error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "detail": "An unexpected internal server error occurred.",
            "status_code": 500,
        },
    )


# Register API routers
app.include_router(health.router)
app.include_router(system.router)
app.include_router(activity.router)
app.include_router(nodes.router)
app.include_router(files.router)
app.include_router(replicas.router)
app.include_router(repair.router)
app.include_router(rebalance.router)
app.include_router(integrity.router)
app.include_router(supabase_router.router)
app.include_router(auth.router)

FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    for subdir in ("css", "js", "assets"):
        target = FRONTEND_DIR / subdir
        if not target.exists():
            try:
                target.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        if target.exists():
            app.mount(f"/{subdir}", StaticFiles(directory=str(target)), name=subdir)


@app.get("/")
async def root_entrypoint(request: Request):
    accept = request.headers.get("accept", "")
    index_file = FRONTEND_DIR / "index.html"
    if "text/html" in accept and index_file.exists():
        return FileResponse(str(index_file))
    if index_file.exists() and "application/json" not in accept:
        return FileResponse(str(index_file))
    return {
        "service": settings.app_name,
        "status": "online",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/index.html")
async def index_html_entrypoint():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse(status_code=404, content={"error": "Not Found"})


@app.get("/favicon.ico")
async def favicon_entrypoint():
    from fastapi import Response
    return Response(status_code=204)
