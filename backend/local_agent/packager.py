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

:: 2. Interactive Folder Configuration (Single-folder exclusive mode)
set "CURRENT_FOLDER="
if exist "%NANVI_DIR%\\config.json" (
    for /f "usebackq delims=" %%F in (`%PYTHON_CMD% -c "import json, os; print(json.load(open(r'%NANVI_DIR%\\config.json')).get('folders', [{{}}])[0].get('path', '')) if os.path.exists(r'%NANVI_DIR%\\config.json') else ''" 2^>nul`) do (
        set "CURRENT_FOLDER=%%F"
    )
)

set "TARGET_FOLDER=%~1"

:PROMPT_LOOP
if "!TARGET_FOLDER!"=="" (
    echo.
    echo -------------------------------------------------------------------
    echo  CONFIGURE ACTIVE COMPANY FOLDER
    echo -------------------------------------------------------------------
    if not "!CURRENT_FOLDER!"=="" (
        echo  Currently active folder:
        echo    !CURRENT_FOLDER!
        echo.
        echo  Press [ENTER] to continue with this folder, OR
        echo  Enter a new folder path to switch to a different folder:
    ) else (
        echo  Please enter or paste the full path of the company folder
        echo  you want Nanvi AI to access (e.g. C:\MyCompanyFiles or D:\Projects):
    )
    echo.
    set /p "USER_INPUT=Folder Path: "
    if "!USER_INPUT!"=="" (
        if not "!CURRENT_FOLDER!"=="" (
            set "TARGET_FOLDER=!CURRENT_FOLDER!"
        ) else (
            echo.
            echo [!] Folder path cannot be empty.
            echo.
            goto PROMPT_LOOP
        )
    ) else (
        set "TARGET_FOLDER=!USER_INPUT!"
    )
)

:: Clean quotes and whitespace
set "TARGET_FOLDER=!TARGET_FOLDER:"=!"
set "TARGET_FOLDER=!TARGET_FOLDER:'=!"
for /f "tokens=* delims= " %%A in ("!TARGET_FOLDER!") do set "TARGET_FOLDER=%%A"

:: Validate directory exists
%PYTHON_CMD% -c "import sys, os; sys.exit(0 if os.path.isdir(sys.argv[1]) else 1)" "!TARGET_FOLDER!" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] The directory "!TARGET_FOLDER!" does not exist or is not a folder.
    echo Please verify the path and enter a valid existing folder.
    echo.
    set "TARGET_FOLDER="
    goto PROMPT_LOOP
)

:: 3. Save pre-configured config.json with ONLY this folder
%PYTHON_CMD% -c "import json, os, sys; p = sys.argv[1]; cfg = {{'server_url': '{clean_server}', 'token': '{pairing_token}', 'display_name': '{clean_display}', 'folders': [{{'path': os.path.abspath(p), 'display_name': os.path.basename(os.path.abspath(p)) or p}}]}}; json.dump(cfg, open(r'%NANVI_DIR%\\config.json', 'w'), indent=2); os.makedirs(os.path.expanduser('~'), exist_ok=True); json.dump(cfg, open(os.path.expanduser('~/.nanvi_local_agent_config.json'), 'w'), indent=2)" "!TARGET_FOLDER!"

echo.
echo ===================================================================
echo  FOLDER CONNECTED SUCCESSFULLY!
echo  Active Folder: !TARGET_FOLDER!
echo  * Nanvi AI will ONLY access this specific folder.
echo  * To change the folder later, simply run this BAT file again.
echo ===================================================================
echo.

:: 4. Unpack GUI Python script using PowerShell (safe from antivirus false positives)
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

:: 5. Verify extraction succeeded
if not exist "%NANVI_DIR%\\nanvi_gui_agent.py" (
    echo.
    echo [!] Could not unpack the Nanvi agent helper.
    echo Please make sure your antivirus is not blocking file extraction in %LOCALAPPDATA%.
    echo.
    pause
    exit /b 1
)

:: 6. Launch the clean white GUI window
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
