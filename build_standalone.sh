#!/bin/bash
# Builds a self-contained standalone binary (noSteam2Steam.bin) for SteamOS / Linux.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Building NoSteam2Steam Standalone Executable ==="

PYTHON_BIN="python3"
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
fi

if ! "$PYTHON_BIN" -c "import PyInstaller" &> /dev/null; then
    echo "PyInstaller not detected. Installing PyInstaller..."
    "$PYTHON_BIN" -m pip install pyinstaller
fi

"$PYTHON_BIN" -m PyInstaller \
    --onefile \
    --name "noSteam2Steam.bin" \
    --collect-all "nosteam2steam" \
    --add-data "assets:assets" \
    --clean \
    noSteam2Steam.py

echo ""
echo "Build successful! Standalone binary is located at:"
echo "  $SCRIPT_DIR/dist/noSteam2Steam.bin"

