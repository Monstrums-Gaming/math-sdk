#!/usr/bin/env bash
# Serve the Cash Paradise frontend demo locally over HTTP.
#
# The demo uses ES module imports (app.js -> prizes.js), so it must be served
# over http:// — opening index.html via file:// will not work.
#
# Usage:
#   ./run.sh            # serve on http://localhost:8000
#   ./run.sh 3000       # serve on a custom port
set -euo pipefail

# Serve from the directory this script lives in, regardless of cwd.
cd "$(dirname "$0")"

PORT="${1:-7800}"
URL="http://localhost:${PORT}"

echo "Cash Paradise demo → ${URL}"
echo "  LOCAL SIM:  ${URL}"
echo "  LIVE RGS:   ${URL}/?sessionID=<session>&currency=USD&mode=base"
echo "Press Ctrl+C to stop."
echo

# Open the browser once the server is up (macOS `open`, Linux `xdg-open`).
( sleep 1; (command -v open >/dev/null && open "$URL") \
            || (command -v xdg-open >/dev/null && xdg-open "$URL") ) >/dev/null 2>&1 &

exec python3 -m http.server "$PORT"
