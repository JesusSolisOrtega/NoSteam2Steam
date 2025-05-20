#!/bin/bash

source "$(dirname "$0")/../variables.txt"

source "$(dirname "$0")/slug_generation.sh"
source "$(dirname "$0")/config_extraction.sh"
source "$(dirname "$0")/game_search.sh"
source "$(dirname "$0")/utils.sh"
source "$(dirname "$0")/detect_game.sh"
source "$(dirname "$0")/search_mode.sh"
source "$(dirname "$0")/dialogs.sh"  

main() {
    check_dependencies

    games_data=$(load_games_data)

    local exe_path=$(select_exe_file)

    if [ -f "$exe_path" ]; then
        while true; do
            search_mode=$(select_search_mode)

            if [ "$search_mode" == "Automática" ]; then
                if handle_automatic_search "$exe_path" "$games_data"; then
                    break
                fi
            else
                if handle_manual_search "$exe_path" "$games_data"; then
                    break
                fi
            fi

            prompt_retry
        done
    else
        echo "Archivo no válido. Inténtalo de nuevo."
    fi
}

main
