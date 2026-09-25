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

from backend.main import app

# Vercel's @vercel/python runtime automatically discovers the `app` ASGI instance.
