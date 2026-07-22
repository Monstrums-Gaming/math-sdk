#!/usr/bin/env bash
# Run the Tap Trade frontend demo (Vite dev server).
# Usage:
#   ./run.sh            # dev server on http://localhost:7921
#
# Production build / preview:
#   npm run build       # emits dist/ (upload its CONTENTS to the Stake Engine Files page)
#   npm run preview     # serves the built dist/ on http://localhost:7922
#
# LIVE mode (real Stake Engine RGS bets):
#   open "http://localhost:7921/?rgs_url=https://<rgs-host>&sessionID=<session>&currency=USD"
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d node_modules ]; then
  echo "Installing dependencies (first run)..."
  npm install
fi
echo "Rebuild the odds bundle after any math change:"
echo "  PYTHONPATH=<repo> <repo>/env/bin/python build_demo_data.py"
echo
exec npm run dev
