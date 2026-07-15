#!/usr/bin/env bash
#
# Build dynamic mystery-box game(s) from JSON manifest(s), in dev or prod mode.
#
# Usage:
#   ./build.sh <dev|prod> [manifest ...]
#
#   ./build.sh dev                     # fast smoke build of every manifest
#   ./build.sh prod                    # full production build of every manifest
#   ./build.sh dev cash_paradise.json  # one manifest (name under manifests/ or a path)
#   NUM_SIMS=5000 ./build.sh dev ...   # override the sim count
#
# Modes (override the manifest's "build" block):
#   dev  -> NUM_SIMS=1000, no compression, no format checks, game_id gets a "_dev"
#           suffix so output lands in games/<game_id>_dev/ and never clobbers prod.
#   prod -> uses the manifest's build values (full sims, compressed, format-checked),
#           output in games/<game_id>/.
#
# NUM_SIMS must keep num_sims*prob integral for every prize (multiple of 500 for the
# sample manifests); in dev a non-integral count only warns, in prod it errors.
#
# Output for each game lands in games/<game_id>[ _dev ]/library/. Works from any cwd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY="$REPO_ROOT/env/bin/python"

usage() { echo "usage: $0 <dev|prod> [manifest ...]" >&2; exit 2; }

[[ $# -ge 1 ]] || usage
MODE="$1"; shift

if [[ ! -x "$PY" ]]; then
  echo "error: venv python not found at $PY — run 'make setup' first." >&2
  exit 1
fi

# Mode presets (env vars consumed by run.py). Respect any value the caller already set.
case "$MODE" in
  dev)
    export NUM_SIMS="${NUM_SIMS:-1000}"
    export COMPRESSION="${COMPRESSION:-false}"
    export RUN_FORMAT_CHECKS="${RUN_FORMAT_CHECKS:-false}"
    export GAME_ID_SUFFIX="${GAME_ID_SUFFIX:-_dev}"
    ;;
  prod)
    # Leave NUM_SIMS/COMPRESSION/RUN_FORMAT_CHECKS unset -> manifest build values.
    export GAME_ID_SUFFIX="${GAME_ID_SUFFIX:-}"
    ;;
  *)
    echo "error: mode must be 'dev' or 'prod', got '$MODE'." >&2
    usage
    ;;
esac

# Resolve the manifests to build: explicit args (filename or path), else all of manifests/.
manifests=()
if [[ $# -gt 0 ]]; then
  for arg in "$@"; do
    if [[ -f "$arg" ]]; then
      manifests+=("$arg")
    elif [[ -f "$SCRIPT_DIR/manifests/$arg" ]]; then
      manifests+=("$SCRIPT_DIR/manifests/$arg")
    else
      echo "error: manifest not found: $arg" >&2
      exit 1
    fi
  done
else
  shopt -s nullglob
  for m in "$SCRIPT_DIR"/manifests/*.json; do
    manifests+=("$m")
  done
  shopt -u nullglob
fi

[[ ${#manifests[@]} -gt 0 ]] || { echo "error: no manifests found in $SCRIPT_DIR/manifests/." >&2; exit 1; }

echo "mode=$MODE  num_sims=${NUM_SIMS:-<manifest>}  compression=${COMPRESSION:-<manifest>}  format_checks=${RUN_FORMAT_CHECKS:-<manifest>}  suffix='${GAME_ID_SUFFIX}'"
for m in "${manifests[@]}"; do
  echo "==> building $(basename "$m")"
  GAME_MANIFEST="$m" "$PY" "$SCRIPT_DIR/run.py"
done

echo "done: built ${#manifests[@]} manifest(s) in $MODE mode."
