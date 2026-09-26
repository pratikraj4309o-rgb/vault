"""
Vercel Serverless Function Entrypoint
Loads the FastAPI application from backend.main with sys.path configuration.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.main import app

__all__ = ["app"]
