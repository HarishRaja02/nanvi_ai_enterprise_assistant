@echo off
title Nanvi Local File Agent for Windows
cd /d "%~dp0"

echo ========================================================
echo       Starting Nanvi Local File Agent for Windows
echo ========================================================

:: 1. Comprehensive Python detection
set "PY_CMD="
for %%P in (pythonw.exe) do if not "%%~$PATH:P"=="" set "PY_CMD=%%~$PATH:P"
if "%PY_CMD%"=="" (
    for %%P in (python.exe) do if not "%%~$PATH:P"=="" set "PY_CMD=%%~$PATH:P"
)
if "%PY_CMD%"=="" (
    for %%P in (py.exe) do if not "%%~$PATH:P"=="" set "PY_CMD=%%~$PATH:P -3"
)
if "%PY_CMD%"=="" (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\pythonw.exe" set "PY_CMD=%%D\pythonw.exe"
        if "%PY_CMD%"=="" if exist "%%D\python.exe" set "PY_CMD=%%D\python.exe"
    )
)
if "%PY_CMD%"=="" (
    for /d %%D in ("%ProgramFiles%\Python3*") do (
        if exist "%%D\pythonw.exe" set "PY_CMD=%%D\pythonw.exe"
        if "%PY_CMD%"=="" if exist "%%D\python.exe" set "PY_CMD=%%D\python.exe"
    )
)
if "%PY_CMD%"=="" (
    where python.exe >nul 2>&1 && set "PY_CMD=python"
)

if "%PY_CMD%"=="" (
    echo.
    echo [!] Python is not installed or not in PATH.
    echo Opening Python official download page...
    start https://www.python.org/downloads/
    echo.
    echo Please install Python (check "Add Python to PATH") and run this file again.
    pause
    exit /b 1
)

:: 2. Ensure default config exists so the agent works immediately
if not exist "config.json" (
    (
    echo {
    echo   "server_url": "http://127.0.0.1:8000",
    echo   "token": "nanvi-local-token",
    echo   "display_name": "Local Agent User"
    echo }
    ) > "config.json"
)

:: 3. Launch GUI Agent by default, or CLI if parameters are passed
if "%~1"=="" (
    if exist "nanvi_gui_agent.py" (
        echo Launching Nanvi Local Agent Window...
        start "" %PY_CMD% nanvi_gui_agent.py
        exit /b 0
    )
)

%PY_CMD% nanvi_local_agent.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Agent exited with error code %ERRORLEVEL%.
    pause
)
