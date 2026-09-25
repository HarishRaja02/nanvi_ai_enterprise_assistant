from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root directory to sys.path so "backend.*" can be imported
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# A Vercel deployment must never silently enable development-only routes.
# Local runs retain the convenient development default.
if not os.getenv("APP_ENV"):
    os.environ["APP_ENV"] = "production" if os.getenv("VERCEL") else "development"

try:
    from backend.main import app
except Exception as exc:
    # Do not return exception details, filesystem paths, or import paths to callers.
    # Those can expose deployment internals when configuration is incomplete.
    import logging
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    logging.exception("Backend initialization failed")
    app = FastAPI(title="Nanvi Vercel Fallback")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
    async def fallback_handler(path: str):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Backend initialization failed on Vercel",
                "detail": "Check Vercel Function logs and required environment variables.",
            },
        )
