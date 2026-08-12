#!/usr/bin/env bash
# Serve the Chicken Crossing frontend demo locally over HTTP.
# The demo fetch()es chicken_rgs.json, so it must be served over http:// (file:// won't work).
# Usage:
#   ./run.sh            # serve on http://localhost:7817
#   ./run.sh 3000       # serve on a custom port
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-7817}"
PAGE="index.html"
URL="http://localhost:${PORT}/${PAGE}"
echo "Chicken Crossing demo → ${URL}"
echo "Rebuild the odds bundle after any math change:"
echo "  PYTHONPATH=<repo> <repo>/env/bin/python ../frontend_demo/build_demo_data.py"
echo "Press Ctrl+C to stop."
echo
( sleep 1; (command -v open >/dev/null && open "$URL") \
            || (command -v xdg-open >/dev/null && xdg-open "$URL") ) >/dev/null 2>&1 &
exec python3 -m http.server "$PORT"
