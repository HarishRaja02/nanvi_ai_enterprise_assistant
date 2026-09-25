from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root directory to sys.path so "backend.*" can be imported
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Default APP_ENV to development if not configured, for safe local / dev runs
if not os.getenv("APP_ENV"):
    os.environ["APP_ENV"] = "development"

try:
    from backend.main import app
except Exception as exc:
    import traceback
    err_tb = traceback.format_exc()
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Nanvi Vercel Fallback")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
    async def fallback_handler(path: str):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Backend initialization failed on Vercel",
                "detail": str(exc),
                "traceback": err_tb,
                "sys_path": sys.path,
                "root_dir": str(root_dir),
                "root_files": os.listdir(str(root_dir)) if root_dir.exists() else "not found",
            },
        )
