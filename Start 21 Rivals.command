#!/bin/bash
# Double-click to start the app. Keep this window open while playing. Close it to stop.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Run 'Setup (run once).command' first."
  read -p "Press Enter to close."
  exit 1
fi
source .venv/bin/activate
(sleep 4 && open "http://localhost:8021") &
caffeinate -i python -m web.app
