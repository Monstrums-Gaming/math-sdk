#!/usr/bin/env bash
# Serve the Kong Climb frontend demo locally over HTTP.
#
# The demo uses an ES module (kong-dice.js) and fetch()es kong_dice_rgs.json, so
# it must be served over http:// — opening the HTML via file:// will not work.
#
# Usage:
#   ./run.sh            # serve on http://localhost:7810
#   ./run.sh 3000       # serve on a custom port
set -euo pipefail

cd "$(dirname "$0")"

PORT="${1:-7810}"
PAGE="index.html"
URL="http://localhost:${PORT}/${PAGE}"

echo "Kong Climb demo → ${URL}"
echo "  LOCAL REPLAY:  ${URL}"
echo "  LIVE RGS:      ${URL}?rgs_url=<host>&sessionID=<session>&currency=USD&mode=over_50"
echo "Press Ctrl+C to stop."
echo

( sleep 1; (command -v open >/dev/null && open "$URL") \
            || (command -v xdg-open >/dev/null && xdg-open "$URL") ) >/dev/null 2>&1 &

exec python3 -m http.server "$PORT"
