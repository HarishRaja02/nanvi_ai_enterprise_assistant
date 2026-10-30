@echo off
title Nanvi Local File Agent for Windows
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ===================================================================
echo             NANVI AI ENTERPRISE ASSISTANT - LOCAL FILE AGENT
echo ===================================================================
echo.

:: 1. Comprehensive Python detection (python.exe preferred for console display)
set "PY_CMD="
for %%P in (python.exe) do if not "%%~$PATH:P"=="" set "PY_CMD=%%~$PATH:P"
if "%PY_CMD%"=="" (
    for %%P in (py.exe) do if not "%%~$PATH:P"=="" set "PY_CMD=%%~$PATH:P -3"
)
if "%PY_CMD%"=="" (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if "%PY_CMD%"=="" if exist "%%D\python.exe" set "PY_CMD=%%D\python.exe"
    )
)
if "%PY_CMD%"=="" (
    for /d %%D in ("%ProgramFiles%\Python3*") do (
        if "%PY_CMD%"=="" if exist "%%D\python.exe" set "PY_CMD=%%D\python.exe"
    )
)
if "%PY_CMD%"=="" (
    for /d %%D in ("%SystemDrive%\Python3*") do (
        if "%PY_CMD%"=="" if exist "%%D\python.exe" set "PY_CMD=%%D\python.exe"
    )
)
if "%PY_CMD%"=="" (
    where python.exe >nul 2>&1 && set "PY_CMD=python"
)

if not "%PY_CMD%"=="" goto PY_FOUND

echo.
echo [!] Python is not installed or not found in system PATH.
echo Opening Python official download page in your browser...
start https://www.python.org/downloads/
echo.
echo Please install Python, check "Add Python to PATH", and run this file again.
echo.
pause
exit /b 1

:PY_FOUND
:: 2. Read existing active folder from config.json if available
set "CURRENT_FOLDER="
if exist "config.json" (
    for /f "usebackq delims=" %%F in (`"%PY_CMD%" -c "import json, os; print(json.load(open('config.json')).get('folders', [{}])[0].get('path', '')) if os.path.exists('config.json') else ''" 2^>nul`) do (
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
:: Clean surrounding quotes and whitespace
set "TARGET_FOLDER=!TARGET_FOLDER:"=!"
set "TARGET_FOLDER=!TARGET_FOLDER:'=!"
for /f "tokens=* delims= " %%A in ("!TARGET_FOLDER!") do set "TARGET_FOLDER=%%A"

:: Check if folder exists
if not exist "!TARGET_FOLDER!\" (
    echo.
    echo [ERROR] The directory "!TARGET_FOLDER!" does not exist or is not a folder.
    echo Please verify the path and enter a valid existing folder.
    echo.
    set "TARGET_FOLDER="
    goto PROMPT_LOOP
)

:: 4. Save to config.json (Exclusively setting this single folder and clearing all others)
"%PY_CMD%" -c "import json, os, sys; p = sys.argv[1]; cfg = json.load(open('config.json')) if os.path.exists('config.json') else {}; cfg.setdefault('server_url', 'http://127.0.0.1:8000'); cfg.setdefault('token', 'nanvi-local-token'); cfg.setdefault('display_name', 'Local Agent User'); cfg['folders'] = [{'path': os.path.abspath(p), 'display_name': os.path.basename(os.path.abspath(p)) or p}]; json.dump(cfg, open('config.json', 'w'), indent=2)" "!TARGET_FOLDER!"

if exist "%USERPROFILE%" (
    copy /y "config.json" "%USERPROFILE%\.nanvi_local_agent_config.json" >nul 2>&1
)

echo.
echo ===================================================================
echo  FOLDER CONNECTED SUCCESSFULLY!
echo  Active Folder: !TARGET_FOLDER!
echo.
echo  * Nanvi AI Assistant will ONLY access this specific folder.
echo  * Any previous folders have been disconnected and purged.
echo  * To change the folder later, simply run this BAT file again.
echo ===================================================================
echo.
echo Starting local indexing and real-time synchronization...
echo.

"%PY_CMD%" nanvi_local_agent.py --folder "!TARGET_FOLDER!" --replace-folders
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Agent exited with code %ERRORLEVEL%.
)
echo.
echo ===================================================================
echo  Nanvi Local Agent stopped.
echo ===================================================================
pause
