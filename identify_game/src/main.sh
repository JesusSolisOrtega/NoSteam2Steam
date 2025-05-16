#!/bin/bash

# Cargar variables desde el archivo de configuración
source "$(dirname "$0")/../variables.txt"

# Importar funciones de otros scripts
source "$(dirname "$0")/slug_generation.sh"
source "$(dirname "$0")/config_extraction.sh"
source "$(dirname "$0")/game_search.sh"
source "$(dirname "$0")/utils.sh"
source "$(dirname "$0")/detect_game.sh"
source "$(dirname "$0")/search_mode.sh"
source "$(dirname "$0")/dialogs.sh"  

# Función principal que orquesta la ejecución
main() {
    # Verificar dependencias
    check_dependencies

    # Cargar datos existentes
    games_data=$(load_games_data)

    # Seleccionar el archivo ejecutable
    local exe_path=$(select_exe_file)

    # Verificar archivo
    if [ -f "$exe_path" ]; then
        while true; do
            # Seleccionar el modo de búsqueda
            search_mode=$(select_search_mode)

            if [ "$search_mode" == "Automática" ]; then
                # Manejar búsqueda automática
                if handle_automatic_search "$exe_path" "$games_data"; then
                    break
                fi
            else
                # Manejar búsqueda manual
                if handle_manual_search "$exe_path" "$games_data"; then
                    break
                fi
            fi

            # Preguntar si desea intentar con otro nombre
            prompt_retry
        done
    else
        echo "Archivo no válido. Inténtalo de nuevo."
    fi
}

# Ejecutar la función principal
main