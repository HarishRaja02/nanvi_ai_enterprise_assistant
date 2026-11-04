@echo off
title Nanvi AI Assistant Launcher
echo ====================================================
echo      NANVI AI ENTERPRISE ASSISTANT - LOCAL RUNNER
echo ====================================================
echo.
cd /d "%~dp0"

:: 1. Start Python Backend in Background if not running
netstat -ano | findstr :8000 >nul 2>&1
if %errorlevel% neq 0 (
    echo [1/2] Starting Python FastAPI Backend on http://127.0.0.1:8000...
    start /b "" "%~dp0venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
    timeout /t 3 /nobreak >nul
) else (
    echo [1/2] Backend is already running on http://127.0.0.1:8000.
)

:: 2. Launch Desktop Application
echo [2/2] Launching Nanvi Desktop Application...
start "" "%~dp0frontend\release\win-unpacked\Nanvi AI Assistant.exe"
echo Done!

