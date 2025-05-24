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

echo "Usando Python: $($PYTHON_CMD --version 2>&1)"

return 0

fi

done

echo "ERROR: Python 3.6+ no encontrado. Instala Python desde Discover o usa:"

echo "flatpak install org.freedesktop.Sdk.Extension.python311"

exit 1

}


detect_python


echo "Instalando $PROJECT_NAME en $INSTALL_DIR..."

mkdir -p "$INSTALL_DIR"


shopt -s dotglob

cp -r ./* "$INSTALL_DIR/" 2>/dev/null

shopt -u dotglob


cd "$INSTALL_DIR"


echo "Creando entorno virtual..."

"$PYTHON_CMD" -m venv "$VENV_NAME"


source "$VENV_NAME/bin/activate"

python -m ensurepip --upgrade

python -m pip install --upgrade pip


if [ -f "requirements.txt" ]; then

echo "Instalando dependencias..."

pip install -r requirements.txt

else

echo "Advertencia: requirements.txt no encontrado (no se instalaron dependencias)"

fi

deactivate

echo "Creando lanzador para SteamDeck"
cat > "$LAUNCHER_SCRIPT" <<EOL
#!/bin/bash
INSTALL_DIR="\$HOME/Games/noSteam2Steam"
VENV_PATH="\$INSTALL_DIR/venv"
LOG_FILE="\$INSTALL_DIR/launch_debug.log"

> "\$LOG_FILE"

echo "--- DEBUG DE LANZAMIENTO ---" &>> "\$LOG_FILE"
echo "Fecha y Hora de lanzamiento: \$(date)" &>> "\$LOG_FILE"
echo "Argumentos recibidos: \$@" &>> "\$LOG_FILE"

source "\$VENV_PATH/bin/activate"

python "\$INSTALL_DIR/noSteam2Steam.py" "\$@" &>> "\$LOG_FILE"

deactivate
EOL

chmod +x "$LAUNCHER_SCRIPT"


cat > "$DESKTOP_FILE" <<EOL
[Desktop Entry]
Name=noSteam2Steam
Comment=Ejecuta noSteam2Steam en modo escritorio
Exec=$INSTALL_DIR/$LAUNCHER_SCRIPT
Icon=$ICON_PATH
Terminal=true
Type=Application
Categories=Game;
EOL

chmod +x "$DESKTOP_FILE"


echo "¡Instalación completada!"
echo "1. Directorio: $INSTALL_DIR"
echo "2. Lanzador: $INSTALL_DIR/$LAUNCHER_SCRIPT"
echo "3. Acceso directo creado: $DESKTOP_FILE"

chmod +x ~/Games/noSteam2Steam/noSteam2Steam.py
chmod +x ~/Games/noSteam2Steam/launch.sh
