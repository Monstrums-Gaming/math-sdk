#!/usr/bin/env bash
# Serve the Market Crash (2_8) frontend demo.
#
# A plain static server is required rather than opening index.html directly: the page
# fetches market_crash_rgs.json, and file:// requests are blocked by CORS.
#
#   ./run.sh                 # LOCAL mode — replays the published odds + real crash points
#   PORT=8123 ./run.sh       # different port
#
# LIVE mode against a real RGS (no server restart needed, just the query string):
#   http://localhost:7921/?rgs_url=<url>&sessionID=<id>&currency=USD
#
# Regenerate the odds bundle after any math rebuild:
#   PYTHONPATH="$PWD" ./env/bin/python games/2_8_market_crash/frontend_demo/build_demo_data.py
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-7921}"

if [ ! -f "$HERE/market_crash_rgs.json" ]; then
  echo "market_crash_rgs.json is missing — run build_demo_data.py first (see header)." >&2
  exit 1
fi

echo "Market Crash demo -> http://localhost:${PORT}/"
( sleep 1; (command -v open >/dev/null && open "http://localhost:${PORT}/") || true ) &
cd "$HERE"
exec python3 -m http.server "$PORT"
