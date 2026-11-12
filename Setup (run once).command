#!/bin/bash
# Double-click this file once to install the 21 Rivals app.
cd "$(dirname "$0")"
echo "Setting up 21 Rivals..."
PY=""
for p in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v $p >/dev/null 2>&1; then
    if $p -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then PY=$p; break; fi
  fi
done
if [ -z "$PY" ]; then
  echo ""
  echo "Your Python is too old (need 3.10 or newer)."
  echo "Opening the download page: install Python 3.12, then double-click this file again."
  open "https://www.python.org/downloads/macos/"
  read -p "Press Enter to close."
  exit 1
fi
echo "Using $($PY --version)"
$PY -m venv .venv && source .venv/bin/activate && pip install -q --upgrade pip && pip install -q -r requirements.txt
if [ $? -eq 0 ]; then
  echo ""
  echo "DONE. Now double-click 'Start 21 Rivals.command' to run the app."
else
  echo ""
  echo "Something went wrong. Take a screenshot of this window and send it over."
fi
read -p "Press Enter to close."
