@echo off
REM One-click startup with pre-flight validation (FR-19). Windows / cmd.exe.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
set "SKIP_UI=0"
if "%~1"=="--no-ui" set "SKIP_UI=1"

echo.
echo Adaptive Knowledge-to-Action Copilot
echo ------------------------------------

REM --- Environment ---------------------------------------------------------
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :fail
)

"%PY%" -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo Installing backend dependencies...
    "%PY%" -m pip install --upgrade pip --quiet
    "%PY%" -m pip install -r backend\requirements.txt --quiet
    if errorlevel 1 goto :fail
)

if not exist ".env" (
    echo.
    echo ERROR: .env not found. Copy .env.example to .env and fill it in:
    echo     copy .env.example .env
    echo.
    exit /b 1
)

if "%SKIP_UI%"=="0" (
    if not exist "frontend\node_modules" (
        echo Installing frontend dependencies...
        pushd frontend
        call npm install --silent
        popd
    )
)

REM --- Pre-flight ----------------------------------------------------------
if "%SKIP_UI%"=="1" (
    "%PY%" backend\scripts\preflight.py --skip-node
) else (
    "%PY%" backend\scripts\preflight.py
)
if errorlevel 1 (
    echo Startup aborted: pre-flight failed.
    exit /b 1
)

REM --- Seed ----------------------------------------------------------------
REM Idempotent and skipped when the stores already hold data, so a normal
REM restart does not pay the embedding cost.
"%PY%" backend\scripts\seed_data.py --if-empty
if errorlevel 1 (
    echo Startup aborted: seeding failed.
    exit /b 1
)

REM --- Launch --------------------------------------------------------------
REM Separate windows so Ctrl-C in either terminates only that service and
REM leaves a readable log behind.
echo Starting backend on http://127.0.0.1:8787 ...
start "Copilot Backend" cmd /k "cd backend && ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8787"

if "%SKIP_UI%"=="0" (
    echo Starting frontend on http://127.0.0.1:5173 ...
    start "Copilot Frontend" cmd /k "cd frontend && npm run dev"
)

echo.
echo Running. Close the spawned windows to stop.
exit /b 0

:fail
echo.
echo Startup failed.
exit /b 1
