#!/usr/bin/env bash
#
# Start the mystery-box build service (FastAPI + uvicorn).
#
# Usage:
#   API_KEY=changeme ./service/run_service.sh            # 0.0.0.0:8000
#   API_KEY=changeme HOST=127.0.0.1 PORT=9000 ./service/run_service.sh
#
# Requires the project venv (make setup) with fastapi + uvicorn installed
# (they are in requirements.txt).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PY="$REPO_ROOT/env/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "error: venv python not found at $PY — run 'make setup' first." >&2
  exit 1
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

cd "$REPO_ROOT"
exec "$PY" -m uvicorn service.app:app --host "$HOST" --port "$PORT" "$@"
