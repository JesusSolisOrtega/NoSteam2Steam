#!/bin/bash

# Función para buscar juegos en SteamDB por AppID
get_game_from_steamdb_by_app_id() {
    local app_id="$1"
    local url="https://steamdb.info/app/$app_id/"
    local response=$(curl -s -A "Mozilla/5.0" "$url")

    if [ $? -eq 0 ] && echo "$response" | grep -i "app_" >/dev/null; then
        local game_title=$(echo "$response" | grep -i "app_" | head -n 1 | sed 's/.*">\([^<]*\)<.*/\1/')
        if [ -n "$game_title" ]; then
            echo "{
                \"status\": \"found\",
                \"matches\": [{
                    \"name\": \"$game_title\",
                    \"slug\": \"\",
                    \"source\": \"SteamDB\",
                    \"platforms\": [\"PC\"],
                    \"released\": \"\",
                    \"background_image\": \"\",
                    \"rating\": null,
                    \"metacritic\": null,
                    \"banner_url\": \"\",
                    \"icon_url\": \"\",
                    \"coverart\": \"\",
                    \"providers\": [],
                    \"user_selected\": true
                }]
            }"
            return
        fi
    fi
    echo "null"
}

# Función para buscar juegos en SteamDB por nombre
get_game_from_steamdb_by_name() {
    local game_name="$1"
    local url="https://steamdb.info/search/?a=app&q=$game_name"
    local response=$(curl -s -A "Mozilla/5.0" "$url")

    if [ $? -eq 0 ] && echo "$response" | grep -i "app_" >/dev/null; then
        local game_title=$(echo "$response" | grep -i "app_" | head -n 1 | sed 's/.*">\([^<]*\)<.*/\1/')
        if [ -n "$game_title" ]; then
            echo "{
                \"status\": \"found\",
                \"matches\": [{
                    \"name\": \"$game_title\",
                    \"slug\": \"\",
                    \"source\": \"SteamDB\",
                    \"platforms\": [\"PC\"],
                    \"released\": \"\",
                    \"background_image\": \"\",
                    \"rating\": null,
                    \"metacritic\": null,
                    \"banner_url\": \"\",
                    \"icon_url\": \"\",
                    \"coverart\": \"\",
                    \"providers\": [],
                    \"user_selected\": true
                }]
            }"
        else
            echo "null"
        fi
    else
        echo "null"
    fi
}

# Función para buscar juegos en RAWG por nombre
get_game_from_rawg_by_name() {
    local game_name="$1"
    local url="https://api.rawg.io/api/games?search=${game_name}&search_precise=false&page_size=5"
    local response=$(curl -s -A "Mozilla/5.0" "$url")

    if [ $? -eq 0 ] && echo "$response" | jq empty 2>/dev/null; then
        local count=$(echo "$response" | jq '.results | length')
        if [ -n "$count" ] && [ "$count" -gt 0 ]; then
            echo "$response" | jq '{
                status: "found",
                matches: [.results[] | {
                    name: .name,
                    slug: .slug,
                    source: "RAWG",
                    platforms: [.platforms[].platform.name],
                    released: .released,
                    background_image: .background_image,
                    rating: .rating,
                    metacritic: .metacritic,
                    banner_url: "",
                    icon_url: "",
                    coverart: "",
                    providers: [],
                    user_selected: true
                }]
            }'
        else
            echo "null"
        fi
    else
        echo "null"
    fi
}

# Función para buscar juegos en Lutris por nombre
get_game_from_lutris_by_name() {
    local game_name="$1"
    game_name=$(echo "$game_name" | tr -d '[](){}' | sed 's/[0-9]*$//' | tr ' ' '+')
    local url="https://lutris.net/api/games?search=$game_name&search_exact=false"
    local response=$(curl -s "$url")

    if [ $? -eq 0 ] && echo "$response" | jq empty 2>/dev/null; then
        local count=$(echo "$response" | jq '.results | length')
        if [ -n "$count" ] && [ "$count" -gt 0 ]; then
            echo "$response" | jq '{
                status: "found",
                matches: [.results[] | {
                    name: .name,
                    slug: .slug,
                    source: "Lutris",
                    platforms: [.platforms[].name],
                    released: .year,
                    background_image: "",
                    rating: null,
                    metacritic: null,
                    banner_url: .banner_url,
                    icon_url: .icon_url,
                    coverart: .coverart,
                    providers: [.provider_games[] | {
                        name: .name,
                        service: .service,
                        id: .slug
                    }],
                    user_selected: true
                }]
            }' 2>/dev/null || echo "null"
        else
            echo "null"
        fi
    else
        echo "null"
    fi
}
