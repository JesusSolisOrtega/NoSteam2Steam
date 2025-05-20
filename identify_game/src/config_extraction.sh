#!/bin/bash

# Función para extraer el AppId de archivos de configuración
extract_app_id() {
    local exe_path="$1"
    local app_id=""

    app_id=$(grep -E "AppId|appid" "$(dirname "$exe_path")"/*.ini 2>/dev/null | grep -Eo '[0-9]+' | grep -v '^#' | head -n 1 || true)

    if [ -z "$app_id" ]; then
        if [ -f "$(dirname "$exe_path")/steam_appid.txt" ]; then
            app_id=$(grep -Eo '[0-9]+' "$(dirname "$exe_path")/steam_appid.txt" || true)
        fi
    fi

    if [ -n "$app_id" ]; then
        log_data "AppId found in configuration files: $app_id"
    fi

    echo "$app_id"
}

# Función para buscar el nombre del juego en archivos adicionales
search_game_name_in_files() {
    local exe_path="$1"
    local game_dir
    local game_name=""
    local search_results=""

    game_dir=$(dirname "$exe_path")

    # Buscar en archivos .ini, .pak, .pck, .xml, .json, .cfg, o globalgamemanagers
    for file in "$game_dir"/*.ini "$game_dir"/*.pak "$game_dir"/*.pck "$game_dir"/*.xml "$game_dir"/*.json "$game_dir"/*.cfg "$game_dir"/globalgamemanagers; do
        if [ -f "$file" ]; then
            game_name=$(strings "$file" | grep -E "AppName|GameName|ProductName" | head -n 1 | cut -d'=' -f2- || true)
            if [ -n "$game_name" ]; then
                log_data "Game name found in file $file: $game_name"
                break
            fi
        fi
    done

    if [ -n "$game_name" ] && [[ "$game_name" == *:* ]]; then
        local base_name="${game_name%%:*}"
        search_results=$(search_game "$game_name" "")
        if [ "$(echo "$search_results" | jq '.matches | length')" -eq 0 ]; then
            search_results=$(search_game "$base_name" "")
        fi
        echo "$search_results"
    else
        echo "$game_name"
    fi
}

# Función para extraer información de configuración
extract_config_info() {
    local exe_path="$1"
    local config_info=""

    config_info=$(extract_app_id "$exe_path")
    if [ -z "$config_info" ]; then
        config_info=$(search_game_name_in_files "$exe_path")
    fi

    echo "$config_info"
}
