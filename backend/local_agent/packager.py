"""Generates ready-to-run 1-click Windows zip package for Nanvi Local File Agent."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path


def generate_agent_zip(server_url: str, pairing_token: str, display_name: str = "") -> bytes:
    """Build a pre-configured, double-clickable zip package for Windows users."""
    script_path = Path(__file__).resolve().parent / "client_agent.py"
    if not script_path.exists():
        script_path = Path(__file__).resolve().parents[2] / "local_agent" / "nanvi_local_agent.py"

    agent_code = script_path.read_text(encoding="utf-8")

    config_data = {
        "server_url": server_url.rstrip("/"),
        "token": pairing_token,
        "display_name": display_name,
    }

    bat_content = f"""@echo off
title Nanvi Assistant - Local File Agent
cd /d "%~dp0"
echo ===================================================================
echo             NANVI AI ENTERPRISE ASSISTANT FOR WINDOWS
echo ===================================================================
echo.
echo Checking for Python...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Python was not found. Opening the official Python installer page...
    start https://www.python.org/downloads/
    echo Please install Python and check "Add Python to PATH", then run this file again.
    pause
    exit /b 1
)

echo [OK] Python is installed.
echo.
echo Starting Nanvi Agent...
echo Connected to: {server_url}
echo.
echo ===================================================================
echo  * You can now return to the Nanvi website to select folders!
echo  * You can MINIMIZE this black window while you work.
echo  * In this window, type "browse" to open a Windows folder picker.
echo ===================================================================
echo.
python nanvi_local_agent.py
pause
"""

    readme_content = f"""===================================================================
               NANVI LOCAL FILE AGENT - QUICK START
===================================================================

Hello {display_name or "there"}!

This helper allows the Nanvi AI website to securely search
approved folders on your personal Windows computer (like PDF, Word,
Excel, and text files).

HOW TO RUN:
1. Double-click "Start_Nanvi_Agent.bat".
2. A window will open showing "Connected". You can minimize it.
3. In your web browser on the Nanvi website, click "+ Add Folder"
   (or type "browse" in the window) to select your folders.

That is all! Nanvi will now be able to answer questions using your
personal files with direct citations.
===================================================================
"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Nanvi_Local_Agent/nanvi_local_agent.py", agent_code)
        zf.writestr("Nanvi_Local_Agent/config.json", json.dumps(config_data, indent=2))
        zf.writestr("Nanvi_Local_Agent/Start_Nanvi_Agent.bat", bat_content)
        zf.writestr("Nanvi_Local_Agent/README.txt", readme_content)

    buf.seek(0)
    return buf.read()
