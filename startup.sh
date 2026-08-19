#!/usr/bin/env bash
# One-click startup with pre-flight validation (FR-19).
# Works on Linux/macOS and on Windows under Git Bash.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Windows venvs put executables in Scripts/, POSIX in bin/.
if [ -d ".venv/Scripts" ]; then VENV_BIN=".venv/Scripts"; else VENV_BIN=".venv/bin"; fi
PY="$VENV_BIN/python"

SKIP_UI=0
for arg in "$@"; do
  [ "$arg" = "--no-ui" ] && SKIP_UI=1
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

echo "Starting backend on http://127.0.0.1:8787 ..."
(cd backend && "../$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8787) &
PIDS+=($!)

if [ "$SKIP_UI" -eq 0 ]; then
  echo "Starting frontend on http://127.0.0.1:5173 ..."
  (cd frontend && npm run dev) &
  PIDS+=($!)
fi

echo ""
echo "Running. Press Ctrl-C to stop."
wait
