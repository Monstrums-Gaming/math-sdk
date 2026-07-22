#!/usr/bin/env bash
# Serve the Tap Trade frontend demo locally over HTTP.
# The demo fetch()es tap_trade_rgs.json, so it must be served over http:// (file:// won't work).
# Usage:
#   ./run.sh            # serve on http://localhost:7921
#   ./run.sh 3000       # serve on a custom port
#
# LIVE mode (real Stake Engine RGS bets):
#   open "http://localhost:7921/index.html?rgs_url=https://<rgs-host>&sessionID=<session>&currency=USD"
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-7921}"
PAGE="index.html"
URL="http://localhost:${PORT}/${PAGE}"
echo "Tap Trade demo → ${URL}"
echo "Rebuild the odds bundle after any math change:"
echo "  PYTHONPATH=<repo> <repo>/env/bin/python build_demo_data.py"
echo "Press Ctrl+C to stop."
echo
( sleep 1; (command -v open >/dev/null && open "$URL") \
            || (command -v xdg-open >/dev/null && xdg-open "$URL") ) >/dev/null 2>&1 &
exec python3 -m http.server "$PORT"
