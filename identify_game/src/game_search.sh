#!/bin/bash

# Import fetchers
source "$(dirname "$0")/game_fetchers.sh"
source "$(dirname "$0")/slug_generation.sh"

consolidate_results() {
    local results="$1"
    echo "$results" | jq '{
        matches: [
            .matches |
            map({
                name: (.name | ascii_downcase | gsub("\\s+"; " ")),
                source: (.source // "" | ascii_downcase),
                released: (.released // "" | tostring),  # Convertir a cadena
                original: .
            }) |
            group_by(.name + .source + .released)[] |  # Concatenar cadenas
            .[0].original
        ]
    }'
}

process_search() {
    local query="$1"
    local search_type="$2"  # "slug", "config" o "name"
    local results='{"matches": []}'
    
    case "$search_type" in
        "slug")
            lutris_results=$(get_game_from_lutris_by_name "$query")
            ;;
        "config")
            local config_slug=$(generate_slug "$query")
            lutris_results=$(get_game_from_lutris_by_name "$config_slug")
            ;;
        "name")
            lutris_results=$(get_game_from_lutris_by_name "$query")
            ;;
    esac

    if [ "$lutris_results" != "null" ] && [ -n "$lutris_results" ]; then
        results=$(echo "$results" | jq --argjson new_matches "$(echo "$lutris_results" | jq '.matches')" '.matches += $new_matches')
    fi

    echo "$results"
}

# Función principal rediseñada
search_game() {
    local slugs="$1"  # Lista de slugs separados por |
    local app_id="$2"
    local config_name="$3"
    local combined_results='{"matches": []}'
    local search_priority="{}"

    log_data "Iniciando búsqueda para AppId: $app_id, Config Name: $config_name, Slugs: $slugs"

    # Exportar funciones necesarias para xargs
    export -f process_search get_game_from_lutris_by_name generate_slug log_data

    # Búsqueda paralela de slugs
    if [ -n "$slugs" ]; then
        combined_results=$(echo "$slugs" | tr '|' '\n' | \
            xargs -P 4 -I {} bash -c 'process_search "{}" "slug"' | \
            jq -s 'reduce .[] as $item ({"matches": []}; .matches += $item.matches)')
    fi

    # Búsqueda por config_name (solo una vez)
    if [ -n "$config_name" ]; then
        config_results=$(process_search "$config_name" "config")
        combined_results=$(echo "$combined_results" | jq --argjson new_matches "$(echo "$config_results" | jq '.matches')" '.matches += $new_matches')
        search_priority=$(echo "$search_priority" | jq --arg name "$config_name" '. += {($name): 2}')
    fi

    # Búsqueda alternativa si no hay resultados
    if [ "$(echo "$combined_results" | jq '.matches | length')" -eq 0 ]; then
        if [ -n "$config_name" ]; then
            combined_results=$(process_search "$config_name" "name")
        elif [ -n "$slugs" ]; then
            # Usar el primer slug para búsqueda alternativa
            primary_slug=$(echo "$slugs" | cut -d'|' -f1)
            combined_results=$(process_search "$primary_slug" "name")
        fi
    fi

    combined_results=$(consolidate_results "$combined_results")
    echo "$combined_results"
}