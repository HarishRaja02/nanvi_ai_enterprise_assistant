@echo off
title Nanvi AI Enterprise Assistant Launcher
cd /d "%~dp0"

echo ====================================================
echo      NANVI AI ENTERPRISE ASSISTANT - LOCAL RUNNER
echo ====================================================
echo.

:: 1. Check if Python backend is already running on port 8000
netstat -ano | findstr :8000 | findstr LISTENING >nul 2>&1
if %errorlevel% neq 0 (
    echo [1/2] Starting Python FastAPI Backend on http://127.0.0.1:8000...
    if exist "%~dp0venv\Scripts\python.exe" (
        start "Nanvi Backend Server" /min "%~dp0venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
    ) else (
        start "Nanvi Backend Server" /min python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
    )
    :: Wait 3 seconds for server startup (ping is reliable in all batch environments)
    ping 127.0.0.1 -n 4 >nul
) else (
    echo [1/2] Python backend is already running on http://127.0.0.1:8000.
)

:: 2. Launch Desktop Application
echo [2/2] Launching Nanvi Desktop Application...
if exist "%~dp0frontend\release\win-unpacked\Nanvi AI Assistant.exe" (
    start "" "%~dp0frontend\release\win-unpacked\Nanvi AI Assistant.exe"
    echo Done!
) else (
    echo ERROR: Could not find desktop executable at:
    echo   frontend\release\win-unpacked\Nanvi AI Assistant.exe
    echo.
    pause
    exit /b 1
)

:: Give 2 seconds then exit launcher cleanly
ping 127.0.0.1 -n 3 >nul
exit
