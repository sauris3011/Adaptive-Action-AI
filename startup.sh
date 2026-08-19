#!/usr/bin/env bash
# One-click startup with pre-flight validation (FR-19).
# Works on Linux/macOS and on Windows under Git Bash.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Windows venvs put executables in Scripts/, POSIX in bin/.
if [ -d ".venv/Scripts" ]; then VENV_BIN=".venv/Scripts"; else VENV_BIN=".venv/bin"; fi
PY="$VENV_BIN/python"

BACKEND_PORT=8787
FRONTEND_PORT=5173

SKIP_UI=0
RECLAIM=1
for arg in "$@"; do
  case "$arg" in
    --no-ui) SKIP_UI=1 ;;
    # Escape hatch: leave whatever is on the ports alone and let pre-flight
    # fail on it, for when the holder is something you meant to keep.
    --no-reclaim) RECLAIM=0 ;;
  esac
done

echo ""
echo "Adaptive Knowledge-to-Action Copilot"
echo "------------------------------------"

# --- Environment -----------------------------------------------------------
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python -m venv .venv
fi

if ! "$PY" -c "import fastapi" >/dev/null 2>&1; then
  echo "Installing backend dependencies..."
  "$PY" -m pip install --upgrade pip --quiet
  "$PY" -m pip install -r backend/requirements.txt --quiet
fi

if [ ! -f ".env" ]; then
  echo ""
  echo "ERROR: .env not found. Copy .env.example to .env and fill it in:"
  echo "  cp .env.example .env"
  echo ""
  exit 1
fi

if [ "$SKIP_UI" -eq 0 ] && [ ! -d "frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd frontend && npm install --silent)
fi

# --- Reclaim ports ---------------------------------------------------------
# Before pre-flight, never inside it: pre-flight asserts the port is free, and a
# check that repairs what it is checking cannot be trusted to report.
if [ "$RECLAIM" -eq 1 ]; then
  RECLAIM_PORTS="$BACKEND_PORT"
  [ "$SKIP_UI" -eq 0 ] && RECLAIM_PORTS="$RECLAIM_PORTS $FRONTEND_PORT"
  if ! "$PY" backend/scripts/free_ports.py $RECLAIM_PORTS; then
    echo "Startup aborted: could not free the ports."
    exit 1
  fi
fi

# --- Pre-flight ------------------------------------------------------------
PREFLIGHT_ARGS=""
[ "$SKIP_UI" -eq 1 ] && PREFLIGHT_ARGS="--skip-node"
if ! "$PY" backend/scripts/preflight.py $PREFLIGHT_ARGS; then
  echo "Startup aborted: pre-flight failed."
  exit 1
fi

# --- Seed ------------------------------------------------------------------
# Idempotent and skipped when the stores already hold data, so a normal restart
# does not pay the embedding cost.
if ! "$PY" backend/scripts/seed_data.py --if-empty; then
  echo "Startup aborted: seeding failed."
  exit 1
fi

# --- Launch ----------------------------------------------------------------
PIDS=()
shutdown() {
  echo ""
  echo "Shutting down..."
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "Stopped."
}
trap shutdown INT TERM EXIT

echo "Starting backend on http://127.0.0.1:$BACKEND_PORT ..."
(cd backend && "../$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT") &
BACKEND_PID=$!
PIDS+=($BACKEND_PID)

# The UI polls /api from first paint, and uvicorn binds its socket only after its
# lifespan has run. Starting Vite first proxies those first seconds to a port
# nothing is listening on yet, and prints a screen of ECONNREFUSED stack traces
# for a stack that is merely still starting.
#
# --pid gives up the moment the backend dies rather than waiting out the whole
# timeout - but only where $! is a pid the OS knows. Under Git Bash it is an
# MSYS pid, which lives in a different namespace from the Windows one tasklist
# reports, so looking it up finds nothing and calls a perfectly healthy backend
# dead. There, wait on the timeout alone.
WAIT_ARGS=""
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) ;;
  *) WAIT_ARGS="--pid $BACKEND_PID" ;;
esac
if ! "$PY" backend/scripts/wait_for_backend.py "$BACKEND_PORT" $WAIT_ARGS; then
  echo "Startup aborted: the backend did not come up."
  exit 1
fi

if [ "$SKIP_UI" -eq 0 ]; then
  echo "Starting frontend on http://127.0.0.1:$FRONTEND_PORT ..."
  (cd frontend && npm run dev) &
  PIDS+=($!)
fi

echo ""
echo "Running. Press Ctrl-C to stop."
wait
