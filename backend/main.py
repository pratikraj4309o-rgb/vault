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
    try:
        db.initialize_schema()
        node_manager.initialize_nodes()
    except Exception as exc:
        logger.error("Startup initialization error: %s", exc)

    # 2. Start background workers ONLY in persistent server environments (NOT in Vercel serverless)
    is_serverless = os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV") is not None
    tasks = []
    stop_event = asyncio.Event()

    if not is_serverless:
        tasks = [
            asyncio.create_task(start_health_worker(stop_event)),
            asyncio.create_task(start_repair_worker(stop_event)),
            asyncio.create_task(start_integrity_worker(stop_event)),
            asyncio.create_task(start_rebalance_worker(stop_event)),
        ]
        logger.info("%s initialized and ready on http://%s:%d (Background workers active)", settings.app_name, settings.host, settings.port)
    else:
        logger.info("%s running in Serverless mode (Background worker loops disabled for function safety)", settings.app_name)

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


from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError


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


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP_ERROR",
            "detail": exc.detail,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = "; ".join(f"{e.get('loc', ['field'])[-1]}: {e.get('msg', 'invalid')}" for e in errors)
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "detail": msg,
            "status_code": 422,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, StarletteHTTPException):
        return await http_exception_handler(request, exc)
    if isinstance(exc, RequestValidationError):
        return await validation_exception_handler(request, exc)
    logger.error("Unhandled internal error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "detail": str(exc) if str(exc) else "An unexpected internal server error occurred.",
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

def _find_frontend_dir() -> Path:
    for candidate in (BASE_DIR / "public", BASE_DIR / "frontend"):
        if candidate.exists() and (candidate / "index.html").exists():
            return candidate
    return BASE_DIR / "frontend"


FRONTEND_DIR = _find_frontend_dir()

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
    if not index_file.exists():
        for fallback in (BASE_DIR / "public" / "index.html", BASE_DIR / "frontend" / "index.html"):
            if fallback.exists():
                index_file = fallback
                break

    if index_file.exists():
        if "application/json" in accept and "text/html" not in accept:
            return {
                "service": settings.app_name,
                "status": "online",
                "version": "1.0.0",
                "docs": "/docs",
                "health": "/api/health",
            }
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
    if not index_file.exists():
        for fallback in (BASE_DIR / "public" / "index.html", BASE_DIR / "frontend" / "index.html"):
            if fallback.exists():
                index_file = fallback
                break
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse(status_code=404, content={"error": "Not Found"})


@app.get("/favicon.ico")
async def favicon_entrypoint():
    from fastapi import Response
    return Response(status_code=204)
