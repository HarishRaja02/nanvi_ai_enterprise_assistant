"""Generates ready-to-run Windows installer and launcher files for Nanvi Local File Agent."""
from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path


def generate_agent_bat(server_url: str, pairing_token: str, display_name: str = "") -> str:
    """Build a 100% self-contained .bat file that unpacks and opens the white GUI window.

    Requires NO zip extraction and NO command-line knowledge.
    Uses built-in Windows certutil to unpack the Python GUI script directly into %LOCALAPPDATA%\\NanviAgent.
    """
    script_path = Path(__file__).resolve().parent / "gui_agent.py"
    if not script_path.exists():
        script_path = Path(__file__).resolve().parents[2] / "local_agent" / "nanvi_gui_agent.py"

    gui_code = script_path.read_text(encoding="utf-8")
    b64_code = base64.b64encode(gui_code.encode("utf-8")).decode("ascii")

    # Format base64 in 64-character lines for standard PEM format accepted by certutil
    b64_lines = "\n".join(b64_code[i : i + 64] for i in range(0, len(b64_code), 64))

    clean_server = server_url.rstrip("/")
    clean_display = display_name.replace('"', '\\"')

    bat_script = f"""@echo off
title Nanvi Assistant Setup
setlocal EnableDelayedExpansion

set "NANVI_DIR=%LOCALAPPDATA%\\NanviAgent"
if not exist "%NANVI_DIR%" mkdir "%NANVI_DIR%" 2>nul

echo ===================================================================
echo             NANVI AI ENTERPRISE ASSISTANT FOR WINDOWS
echo ===================================================================
echo.
echo Starting Nanvi Local Agent...

:: 1. Verify Python availability
where pythonw.exe >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    where python.exe >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo [!] Python is not installed on this computer.
        echo Opening Python download page in your browser...
        start https://www.python.org/downloads/
        echo.
        echo Please run the installer, make sure to check "Add Python to PATH",
        echo and then run this file again.
        pause
        exit /b 1
    )
)

:: 2. Write pre-configured config.json
(
echo {{
echo   "server_url": "{clean_server}",
echo   "token": "{pairing_token}",
echo   "display_name": "{clean_display}"
echo }}
) > "%NANVI_DIR%\\config.json"

:: 3. Unpack GUI Python script using Windows built-in certutil directly from this file
certutil -decode -f "%~f0" "%NANVI_DIR%\\nanvi_gui_agent.py" >nul 2>&1

:: 4. Launch the clean white GUI window silently
where pythonw.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    start "" pythonw "%NANVI_DIR%\\nanvi_gui_agent.py"
) else (
    start "" python "%NANVI_DIR%\\nanvi_gui_agent.py"
)

exit /b 0

-----BEGIN CERTIFICATE-----
{b64_lines}
-----END CERTIFICATE-----
"""
    return bat_script


def generate_agent_zip(server_url: str, pairing_token: str, display_name: str = "") -> bytes:
    """Build a pre-configured zip package as an alternative download."""
    script_path = Path(__file__).resolve().parent / "gui_agent.py"
    if not script_path.exists():
        script_path = Path(__file__).resolve().parents[2] / "local_agent" / "nanvi_gui_agent.py"

    agent_code = script_path.read_text(encoding="utf-8")

    config_data = {
        "server_url": server_url.rstrip("/"),
        "token": pairing_token,
        "display_name": display_name,
    }

    bat_content = f"""@echo off
title Nanvi Assistant - Local File Agent
cd /d "%~dp0"
where pythonw.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    start "" pythonw nanvi_gui_agent.py
) else (
    start "" python nanvi_gui_agent.py
)
exit /b 0
"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Nanvi_Local_Agent/nanvi_gui_agent.py", agent_code)
        zf.writestr("Nanvi_Local_Agent/config.json", json.dumps(config_data, indent=2))
        zf.writestr("Nanvi_Local_Agent/Start_Nanvi_Agent.bat", bat_content)

    buf.seek(0)
    return buf.read()
