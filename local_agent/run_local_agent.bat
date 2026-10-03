@echo off
title Nanvi Local File Agent
cd /d "%~dp0"
echo ========================================================
echo       Starting Nanvi Local File Agent for Windows
echo ========================================================
python nanvi_local_agent.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Agent exited with error code %ERRORLEVEL%.
    pause
)
