"""
Vercel Serverless API Entrypoint
Re-exports the FastAPI application instance from backend.main.
"""

from backend.main import app

__all__ = ["app"]
