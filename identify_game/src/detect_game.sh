#!/bin/bash


detect_game_from_exe() {
    local exe_path="$1"
    local games_data="$2"
    local game_name="${3:-}"
    local exe_name
    local combined_results='{"matches": []}'
    local search_priority="{}"
    local app_id=""
    local config_name=""

    exe_name=$(basename "$exe_path" | sed 's/\.[^.]*$//')

    log_data "Matching game for executable: $exe_path"

    if [ -z "$game_name" ]; then
        game_name=$(search_game_name_in_files "$exe_path")
        if [ -n "$game_name" ]; then
            search_priority=$(echo "$search_priority" | jq --arg name "$game_name" '. += {($name): 2}')
            log_data "Game name found in files: $game_name"
        fi
    fi

    app_id=$(grep -E "AppId|appid" "$(dirname "$exe_path")"/*.ini 2>/dev/null | grep -Eo '[0-9]+' | head -n 1 || true)
    
    if [ -z "$app_id" ]; then
        if [ -f "$(dirname "$exe_path")/steam_appid.txt" ]; then
            app_id=$(grep -Eo '[0-9]+' "$(dirname "$exe_path")/steam_appid.txt" || true)
        fi
    fi

    if [ -n "$app_id" ]; then
        search_priority=$(echo "$search_priority" | jq --arg app_id "$app_id" '. += {($app_id): 1}')
        log_data "AppId found: $app_id"
    fi

    config_name=$(basename "$exe_path" | sed 's/\.[^.]*$//')

    slugs=()
    slugs+=("$(extract_slug "$exe_name")")
    slugs+=("$(extract_slug_without_hyphens "$exe_name")")
    if [[ "$exe_name" =~ (I|V|X)+$ || "$exe_name" =~ [0-9]+$ ]]; then
        local base_name="${exe_name%${BASH_REMATCH[0]}}"
        slugs+=("$(extract_slug "$base_name")")
        slugs+=("$(extract_slug_without_hyphens "$base_name")")
    fi

    slugs=$(IFS='|'; echo "${slugs[*]}")
    log_data "Starting search for AppId: $app_id, Config Name: $config_name, Slug: $slug"
    results=$(search_game "$slugs" "$app_id" "$config_name")
    combined_results=$(echo "$combined_results" | jq --argjson new_matches "$(echo "$results" | jq '.matches')" '.matches += $new_matches')
    
    if [ "$(echo "$combined_results" | jq '.matches | length')" -gt 0 ]; then
        selected_match=$(select_correct_match "$combined_results" "$exe_name" "$search_priority")
        if [ $? -eq 0 ]; then
            selected_info=$(echo "$selected_match" | jq --arg exe_path "$exe_path" \
                '{
                    name: .name,
                    slug: .slug,
                    source: .source,
                    platforms: .platforms,
                    released: .released,
                    background_image: .background_image,
                    rating: .rating,
                    metacritic: .metacritic,
                    banner_url: .banner_url,
                    icon_url: .icon_url,
                    coverart: .coverart,
                    providers: .providers,
                    exe_path: $exe_path,
                    user_selected: true
                } | with_entries(if .value == null then .value = "" else . end)')
            game_name=$(echo "$selected_info" | jq -r '.name')
            updated_data=$(echo "$games_data" | jq --arg name "$game_name" --argjson info "$selected_info" '. + {($name): $info}')
            log_data "Game found: $game_name"
            echo "$updated_data"
            return 0
        fi
    fi

    log_data "Game not found in any source."
    return 1
}
