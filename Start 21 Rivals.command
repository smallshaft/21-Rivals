#!/bin/bash
# Double-click to start the app. Keep this window open while playing. Close it to stop.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Run 'Setup (run once).command' first."
  read -p "Press Enter to close."
  exit 1
fi
source .venv/bin/activate
# stop any older copy of the app that's still running (it would block the new one)
OLD=$(lsof -ti tcp:8021 2>/dev/null)
if [ -n "$OLD" ]; then echo "Stopping an older copy of the app..."; kill $OLD 2>/dev/null; sleep 1; fi
# compiled-code cache in a folder macOS always lets us write to
export NUMBA_CACHE_DIR="$HOME/Library/Caches/21Rivals/numba"
mkdir -p "$NUMBA_CACHE_DIR"
(sleep 4 && open "http://localhost:8021") &
caffeinate -i python -m web.app
