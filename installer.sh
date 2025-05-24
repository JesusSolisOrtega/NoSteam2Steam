#!/bin/bash

INSTALL_DIR="$HOME/Games/noSteam2Steam"
PROJECT_NAME="noSteam2Steam"
VENV_NAME="venv"
LAUNCHER_SCRIPT="launch.sh"
ICON_PATH="$INSTALL_DIR/icon.png"
DESKTOP_FILE="$HOME/Desktop/noSteam2Steam.desktop"

detect_python() {

for PYTHON_CMD in python3 python; do

if command -v "$PYTHON_CMD" &> /dev/null && \
"$PYTHON_CMD" -c "import sys; exit(0 if sys.version_info >= (3, 6) else 1)"; then
echo "Using Python: $($PYTHON_CMD --version 2>&1)"
return 0
fi

done

echo "ERROR: Python 3.6+ not found. Install Python via Discover or use:"
echo "flatpak install org.freedesktop.Sdk.Extension.python311"
exit 1
}

detect_python

echo "Installing $PROJECT_NAME in $INSTALL_DIR..."

mkdir -p "$INSTALL_DIR"

shopt -s dotglob
cp -r ./* "$INSTALL_DIR/" 2>/dev/null
shopt -u dotglob

cd "$INSTALL_DIR"

echo "Creating virtual environment..."

"$PYTHON_CMD" -m venv "$VENV_NAME"

source "$VENV_NAME/bin/activate"

python -m ensurepip --upgrade
python -m pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
else
    echo "Warning: requirements.txt not found (no dependencies installed)"
fi

deactivate

echo "Creating launcher for SteamDeck..."
cat > "$LAUNCHER_SCRIPT" <<EOL
#!/bin/bash
INSTALL_DIR="\$HOME/Games/noSteam2Steam"
VENV_PATH="\$INSTALL_DIR/venv"
LOG_FILE="\$INSTALL_DIR/launch_debug.log"

> "\$LOG_FILE"

echo "--- LAUNCH DEBUG ---" &>> "\$LOG_FILE"
echo "Launch date and time: \$(date)" &>> "\$LOG_FILE"
echo "Received arguments: \$@" &>> "\$LOG_FILE"

source "\$VENV_PATH/bin/activate"

python "\$INSTALL_DIR/noSteam2Steam.py" "\$@" &>> "\$LOG_FILE"

deactivate
EOL

chmod +x "$LAUNCHER_SCRIPT"

cat > "$DESKTOP_FILE" <<EOL
[Desktop Entry]
Name=noSteam2Steam
Comment=Run noSteam2Steam in Desktop Mode
Exec=$INSTALL_DIR/$LAUNCHER_SCRIPT
Icon=$ICON_PATH
Terminal=true
Type=Application
Categories=Game;
EOL

chmod +x "$DESKTOP_FILE"

echo "Installation completed!"
echo "1. Directory: $INSTALL_DIR"
echo "2. Launcher: $INSTALL_DIR/$LAUNCHER_SCRIPT"
echo "3. Desktop shortcut created: $DESKTOP_FILE"

chmod +x ~/Games/noSteam2Steam/noSteam2Steam.py
chmod +x ~/Games/noSteam2Steam/launch.sh
