"""Generates ready-to-run Windows installer and launcher files for Nanvi Local File Agent."""
from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path


def generate_agent_bat(server_url: str, pairing_token: str, display_name: str = "") -> str:
    """Build a 100% self-contained .bat file that prompts for folder path and runs the agent in terminal.

    Requires NO zip extraction and NO command-line knowledge.
    Uses built-in Windows certutil / PowerShell to unpack the Python agent script directly into %LOCALAPPDATA%\\NanviAgent.
    """
    script_path = Path(__file__).resolve().parent / "client_agent.py"
    if not script_path.exists():
        script_path = Path(__file__).resolve().parents[2] / "local_agent" / "nanvi_local_agent.py"

    agent_code = script_path.read_text(encoding="utf-8")
    b64_code = base64.b64encode(agent_code.encode("utf-8")).decode("ascii")

    # Format base64 in 64-character lines with echo for standard PEM format accepted by certutil
    b64_lines = "\n".join(f"echo {b64_code[i : i + 64]}" for i in range(0, len(b64_code), 64))

    clean_server = server_url.rstrip("/")
    clean_display = display_name.replace('"', '').replace("'", "")

    bat_script = f"""@echo off
title Nanvi Assistant - Local File Agent
setlocal EnableDelayedExpansion

set "NANVI_DIR=%LOCALAPPDATA%\\NanviAgent"
if not exist "%NANVI_DIR%" mkdir "%NANVI_DIR%" 2>nul

echo ===================================================================
echo             NANVI AI ENTERPRISE ASSISTANT FOR WINDOWS
echo ===================================================================
echo.
echo Starting Nanvi Local Agent...

:: 1. Comprehensive Python detection (python.exe preferred for terminal console)
set "PYTHON_CMD="
for %%P in (python.exe) do if not "%%~$PATH:P"=="" set "PYTHON_CMD=%%~$PATH:P"
if "%PYTHON_CMD%"=="" (
    for %%P in (py.exe) do if not "%%~$PATH:P"=="" set "PYTHON_CMD=%%~$PATH:P -3"
)
if "%PYTHON_CMD%"=="" (
    for /d %%D in ("%LOCALAPPDATA%\\Programs\\Python\\Python3*") do (
        if "%PYTHON_CMD%"=="" if exist "%%D\\python.exe" set "PYTHON_CMD=%%D\\python.exe"
    )
)
if "%PYTHON_CMD%"=="" (
    for /d %%D in ("%ProgramFiles%\\Python3*") do (
        if "%PYTHON_CMD%"=="" if exist "%%D\\python.exe" set "PYTHON_CMD=%%D\\python.exe"
    )
)
if "%PYTHON_CMD%"=="" (
    for /d %%D in ("%SystemDrive%\\Python3*") do (
        if "%PYTHON_CMD%"=="" if exist "%%D\\python.exe" set "PYTHON_CMD=%%D\\python.exe"
    )
)
if "%PYTHON_CMD%"=="" (
    where python.exe >nul 2>&1 && set "PYTHON_CMD=python"
)

if not "%PYTHON_CMD%"=="" goto PY_READY

echo.
echo [!] Python is not installed or not in PATH on this computer.
echo Opening Python official download page in your browser...
start https://www.python.org/downloads/
echo.
echo Please install Python, check "Add Python to PATH", and run this file again.
echo.
pause
exit /b 1

:PY_READY
:: 2. Interactive Folder Configuration (Single-folder exclusive mode)
set "CURRENT_FOLDER="
if exist "%NANVI_DIR%\\config.json" (
    for /f "usebackq delims=" %%F in (`"%PYTHON_CMD%" -c "import json, os; print(json.load(open(r'%NANVI_DIR%\\config.json')).get('folders', [{{}}])[0].get('path', '')) if os.path.exists(r'%NANVI_DIR%\\config.json') else ''" 2^>nul`) do (
        set "CURRENT_FOLDER=%%F"
    )
)

set "TARGET_FOLDER=%~1"
if not "!TARGET_FOLDER!"=="" goto VALIDATE_FOLDER

:PROMPT_LOOP
echo -------------------------------------------------------------------
echo  CONFIGURE ACTIVE COMPANY FOLDER
echo -------------------------------------------------------------------
if not "!CURRENT_FOLDER!"=="" (
    echo  Currently active folder:
    echo    !CURRENT_FOLDER!
    echo.
    echo  Press ENTER to continue with this folder, OR
    echo  Enter a new folder path to switch to a different folder:
)
if "!CURRENT_FOLDER!"=="" (
    echo  Please enter or paste the full path of the company folder
    echo  you want Nanvi AI to access. Example: C:\MyCompanyFiles or D:\Projects
)
echo.
set /p "USER_INPUT=Folder Path: "
if "!USER_INPUT!"=="" (
    if not "!CURRENT_FOLDER!"=="" (
        set "TARGET_FOLDER=!CURRENT_FOLDER!"
        goto VALIDATE_FOLDER
    )
    echo.
    echo [!] Folder path cannot be empty.
    echo.
    goto PROMPT_LOOP
)
set "TARGET_FOLDER=!USER_INPUT!"

:VALIDATE_FOLDER
:: Clean quotes and whitespace
set "TARGET_FOLDER=!TARGET_FOLDER:"=!"
set "TARGET_FOLDER=!TARGET_FOLDER:'=!"
for /f "tokens=* delims= " %%A in ("!TARGET_FOLDER!") do set "TARGET_FOLDER=%%A"

:: Validate directory exists
if not exist "!TARGET_FOLDER!\\" (
    echo.
    echo [ERROR] The directory "!TARGET_FOLDER!" does not exist or is not a folder.
    echo Please verify the path and enter a valid existing folder.
    echo.
    set "TARGET_FOLDER="
    goto PROMPT_LOOP
)

:: 3. Save pre-configured config.json with ONLY this folder
"%PYTHON_CMD%" -c "import json, os, sys; p = sys.argv[1]; cfg = {{'server_url': '{clean_server}', 'token': '{pairing_token}', 'display_name': '{clean_display}', 'folders': [{{'path': os.path.abspath(p), 'display_name': os.path.basename(os.path.abspath(p)) or p}}]}}; json.dump(cfg, open(r'%NANVI_DIR%\\config.json', 'w'), indent=2); os.makedirs(os.path.expanduser('~'), exist_ok=True); json.dump(cfg, open(os.path.expanduser('~/.nanvi_local_agent_config.json'), 'w'), indent=2)" "!TARGET_FOLDER!"

echo.
echo ===================================================================
echo  FOLDER CONNECTED SUCCESSFULLY!
echo  Active Folder: !TARGET_FOLDER!
echo  * Nanvi AI will ONLY access this specific folder.
echo  * Any previous folders have been disconnected and purged.
echo  * To change the folder later, simply run this BAT file again.
echo ===================================================================
echo.

:: 4. Unpack Python agent script safely
set "B64_FILE=%TEMP%\\nanvi_agent_b64.txt"
(
echo -----BEGIN CERTIFICATE-----
{b64_lines}
echo -----END CERTIFICATE-----
) > "%B64_FILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$c = (Get-Content -Path '%B64_FILE%' | Where-Object {{ $_ -notmatch '^-' }}) -join ''; [System.IO.File]::WriteAllBytes('%NANVI_DIR%\\nanvi_local_agent.py', [System.Convert]::FromBase64String($c))" >nul 2>&1

if not exist "%NANVI_DIR%\\nanvi_local_agent.py" (
    certutil -decode "%B64_FILE%" "%NANVI_DIR%\\nanvi_local_agent.py" >nul 2>&1
)
del "%B64_FILE%" 2>nul

:: 5. Verify extraction succeeded
if not exist "%NANVI_DIR%\\nanvi_local_agent.py" (
    echo.
    echo [!] Could not unpack the Nanvi agent helper into %NANVI_DIR%.
    echo Please make sure your antivirus is not blocking file creation in %LOCALAPPDATA%.
    echo.
    pause
    exit /b 1
)

:: 6. Launch agent in the current terminal window with live status
echo Starting local indexing and real-time synchronization...
echo.
"%PYTHON_CMD%" "%NANVI_DIR%\\nanvi_local_agent.py" --folder "!TARGET_FOLDER!" --replace-folders
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Agent exited with error code %ERRORLEVEL%.
)

echo.
echo ===================================================================
echo  Nanvi Local Agent stopped.
echo ===================================================================
pause
exit /b 0
"""
    return bat_script


def generate_agent_zip(server_url: str, pairing_token: str, display_name: str = "") -> bytes:
    """Build a pre-configured zip package as an alternative download."""
    script_path = Path(__file__).resolve().parent / "client_agent.py"
    if not script_path.exists():
        script_path = Path(__file__).resolve().parents[2] / "local_agent" / "nanvi_local_agent.py"

    agent_code = script_path.read_text(encoding="utf-8")

    config_data = {
        "server_url": server_url.rstrip("/"),
        "token": pairing_token,
        "display_name": display_name,
    }

    bat_content = r"""@echo off
title Nanvi Assistant - Local File Agent
cd /d "%~dp0"
where python.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python nanvi_local_agent.py
) else (
    py -3 nanvi_local_agent.py
)
pause
exit /b 0
"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Nanvi_Local_Agent/nanvi_local_agent.py", agent_code)
        zf.writestr("Nanvi_Local_Agent/config.json", json.dumps(config_data, indent=2))
        zf.writestr("Nanvi_Local_Agent/Start_Nanvi_Agent.bat", bat_content)

    buf.seek(0)
    return buf.read()
