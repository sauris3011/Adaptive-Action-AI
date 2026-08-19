@echo off
REM One-click startup with pre-flight validation (FR-19). Windows / cmd.exe.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
set "BACKEND_PORT=8787"
set "FRONTEND_PORT=5173"
set "SKIP_UI=0"
set "RECLAIM=1"

REM Flags in any order, unlike the single-argument check this used to do.
:parse_args
if "%~1"=="" goto :args_done
if /I "%~1"=="--no-ui" set "SKIP_UI=1"
REM Escape hatch: leave whatever is on the ports alone and let pre-flight fail
REM on it, for when the holder is something you meant to keep.
if /I "%~1"=="--no-reclaim" set "RECLAIM=0"
shift
goto :parse_args
:args_done

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

REM --- Reclaim ports -------------------------------------------------------
REM Before pre-flight, never inside it: pre-flight asserts the port is free, and
REM a check that repairs what it is checking cannot be trusted to report.
if "%RECLAIM%"=="1" (
    if "%SKIP_UI%"=="1" (
        "%PY%" backend\scripts\free_ports.py %BACKEND_PORT%
    ) else (
        "%PY%" backend\scripts\free_ports.py %BACKEND_PORT% %FRONTEND_PORT%
    )
    if errorlevel 1 (
        echo Startup aborted: could not free the ports.
        exit /b 1
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
echo Starting backend on http://127.0.0.1:%BACKEND_PORT% ...
start "Copilot Backend" cmd /k "cd backend && ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT%"

REM --- Wait for the backend ------------------------------------------------
REM The UI polls /api from first paint, and uvicorn binds its socket only after
REM its lifespan has run. Starting Vite first proxies those first seconds to a
REM port nothing is listening on yet, and prints a screen of ECONNREFUSED stack
REM traces for a stack that is merely still starting. Kept out of an if-block so
REM errorlevel is read when it is set, not when the block was parsed.
"%PY%" backend\scripts\wait_for_backend.py %BACKEND_PORT%
if errorlevel 1 (
    echo Startup aborted: the backend did not come up.
    exit /b 1
)

if "%SKIP_UI%"=="0" (
    echo Starting frontend on http://127.0.0.1:%FRONTEND_PORT% ...
    start "Copilot Frontend" cmd /k "cd frontend && npm run dev"
)

echo.
echo Running. Close the spawned windows to stop.
exit /b 0

:fail
echo.
echo Startup failed.
exit /b 1
