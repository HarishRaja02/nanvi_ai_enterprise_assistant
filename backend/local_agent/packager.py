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

    # Format base64 in 64-character lines with echo for standard PEM format accepted by certutil
    b64_lines = "\n".join(f"echo {b64_code[i : i + 64]}" for i in range(0, len(b64_code), 64))

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

:: 1. Comprehensive Python detection
set "PYTHON_CMD="
for %%P in (pythonw.exe) do if not "%%~$PATH:P"=="" set "PYTHON_CMD=%%~$PATH:P"
if "%PYTHON_CMD%"=="" (
    for %%P in (python.exe) do if not "%%~$PATH:P"=="" set "PYTHON_CMD=%%~$PATH:P"
)
if "%PYTHON_CMD%"=="" (
    for %%P in (py.exe) do if not "%%~$PATH:P"=="" set "PYTHON_CMD=%%~$PATH:P -3"
)
if "%PYTHON_CMD%"=="" (
    for /d %%D in ("%LOCALAPPDATA%\\Programs\\Python\\Python3*") do (
        if exist "%%D\\pythonw.exe" set "PYTHON_CMD=%%D\\pythonw.exe"
        if "%PYTHON_CMD%"=="" if exist "%%D\\python.exe" set "PYTHON_CMD=%%D\\python.exe"
    )
)
if "%PYTHON_CMD%"=="" (
    for /d %%D in ("%ProgramFiles%\\Python3*") do (
        if exist "%%D\\pythonw.exe" set "PYTHON_CMD=%%D\\pythonw.exe"
        if "%PYTHON_CMD%"=="" if exist "%%D\\python.exe" set "PYTHON_CMD=%%D\\python.exe"
    )
)
if "%PYTHON_CMD%"=="" (
    for /d %%D in ("%SystemDrive%\\Python3*") do (
        if exist "%%D\\pythonw.exe" set "PYTHON_CMD=%%D\\pythonw.exe"
        if "%PYTHON_CMD%"=="" if exist "%%D\\python.exe" set "PYTHON_CMD=%%D\\python.exe"
    )
)
if "%PYTHON_CMD%"=="" (
    where python.exe >nul 2>&1 && set "PYTHON_CMD=python"
)

if "%PYTHON_CMD%"=="" (
    echo.
    echo [!] Python is not installed on this computer.
    echo Opening Python official download page in your browser...
    start https://www.python.org/downloads/
    echo.
    echo Please run the installer, make sure to check "Add Python to PATH",
    echo and then run this file again.
    echo.
    pause
    exit /b 1
)

:: 2. Write pre-configured config.json to both app directory and user profile
(
echo {{
echo   "server_url": "{clean_server}",
echo   "token": "{pairing_token}",
echo   "display_name": "{clean_display}"
echo }}
) > "%NANVI_DIR%\\config.json"

copy /y "%NANVI_DIR%\\config.json" "%USERPROFILE%\\.nanvi_local_agent_config.json" >nul 2>&1

:: 3. Unpack GUI Python script using PowerShell (safe from antivirus false positives)
set "B64_FILE=%TEMP%\\nanvi_agent_b64.txt"
(
echo -----BEGIN CERTIFICATE-----
{b64_lines}
echo -----END CERTIFICATE-----
) > "%B64_FILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$c = (Get-Content -Path '%B64_FILE%' | Where-Object {{ $_ -notmatch '^-' }}) -join ''; [System.IO.File]::WriteAllBytes('%NANVI_DIR%\\nanvi_gui_agent.py', [System.Convert]::FromBase64String($c))" >nul 2>&1

if not exist "%NANVI_DIR%\\nanvi_gui_agent.py" (
    certutil -decode "%B64_FILE%" "%NANVI_DIR%\\nanvi_gui_agent.py" >nul 2>&1
)
del "%B64_FILE%" 2>nul

:: 4. Verify extraction succeeded
if not exist "%NANVI_DIR%\\nanvi_gui_agent.py" (
    echo.
    echo [!] Could not unpack the Nanvi agent helper.
    echo Please make sure your antivirus is not blocking file extraction in %LOCALAPPDATA%.
    echo.
    pause
    exit /b 1
)

:: 5. Launch the clean white GUI window
echo Launching Nanvi Local File Agent...
start "" %PYTHON_CMD% "%NANVI_DIR%\\nanvi_gui_agent.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Agent failed to launch. Error code: %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

exit /b 0
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
