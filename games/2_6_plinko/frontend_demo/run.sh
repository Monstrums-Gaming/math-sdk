#!/usr/bin/env bash
# Serve the Plinko frontend demo locally over HTTP.
#
# The demo fetch()es plinko_rgs.json (the published-math bundle), so it must be
# served over http:// — opening the HTML via file:// will not work.
#
# Usage:
#   ./run.sh            # serve on http://localhost:7816
#   ./run.sh 3000       # serve on a custom port
set -euo pipefail

cd "$(dirname "$0")"

PORT="${1:-7816}"
PAGE="plinko.html"
URL="http://localhost:${PORT}/${PAGE}"

echo "Plinko demo → ${URL}"
echo "Rebuild the odds bundle after any math change:"
echo "  PYTHONPATH=<repo> <repo>/env/bin/python ../frontend_demo/build_demo_data.py"
echo "Press Ctrl+C to stop."
echo

( sleep 1; (command -v open >/dev/null && open "$URL") \
            || (command -v xdg-open >/dev/null && xdg-open "$URL") ) >/dev/null 2>&1 &

exec python3 -m http.server "$PORT"
