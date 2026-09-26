"""
NexStore VAULT - Application Entrypoint
Exports the FastAPI app instance from backend.main for standard ASGI runners and deployment runtimes.
"""

from backend.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn
    from backend.config import settings

    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=True)
