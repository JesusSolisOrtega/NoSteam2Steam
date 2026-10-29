#!/usr/bin/env bash
# Root development and execution launcher for NoSteam2Steam

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ -f "$VENV_DIR/bin/python" ]; then
    exec "$VENV_DIR/bin/python" "$SCRIPT_DIR/noSteam2Steam.py" "$@"
elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    exec "$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/noSteam2Steam.py" "$@"
else
    exec python3 "$SCRIPT_DIR/noSteam2Steam.py" "$@"
fi

