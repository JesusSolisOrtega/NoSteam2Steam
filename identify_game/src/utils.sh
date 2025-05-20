#!/bin/bash

LOG_FILE="$(pwd)/identify_game.log"

check_dependencies() {
    local missing_deps=()
    local failed_installs=()
    
    if ! command -v jq >/dev/null 2>&1; then
        missing_deps+=("jq")
    fi
    
    if ! command -v curl >/dev/null 2>&1; then
        missing_deps+=("curl")
    fi
    
    if ! command -v zenity >/dev/null 2>&1; then
        missing_deps+=("zenity")
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        echo "Faltan las siguientes dependencias: ${missing_deps[*]}"
        echo "Intentando instalar automáticamente..."
        
        for dep in "${missing_deps[@]}"; do
            if ! install_dependencies "$dep"; then
                failed_installs+=("$dep")
            fi
        done
        
        if [ ${#failed_installs[@]} -ne 0 ]; then
            echo "Error: No se pudieron instalar todas las dependencias."
            echo "Por favor, instala manualmente: ${failed_installs[*]}"
            echo "Puedes usar: sudo pacman -S ${failed_installs[*]}"
            exit 1
        fi
    fi
}

log_data() {
    local data="$@"
    local log_dir
    log_dir=$(dirname "$LOG_FILE")
    mkdir -p "$log_dir"
    echo "$data" >> "$LOG_FILE"
}

load_games_data() {
    if [ -f "$GAMES_JSON_FILE" ]; then
        cat "$GAMES_JSON_FILE"
    else
        echo '{}'
    fi
}

save_games_data() {
    local data="$1"
    echo "$data" > "$GAMES_JSON_FILE"
}

process_results() {
    local results="$1"
    local games_data="$2"

    local new_games=$(echo "$results" | jq '.matches')
    local updated_games=$(echo "$games_data" | jq --argjson new_games "$new_games" '.games += $new_games')

    echo "$updated_games"
}

levenshtein() {
    if [ "$#" -ne 2 ]; then
        echo "Usage: levenshtein string1 string2" >&2
        return 1
    fi

    local str1="$1"
    local str2="$2"
    local len1=${#str1}
    local len2=${#str2}
    local d i j cost

    for ((i=0; i<=len1; i++)); do
        d[i,0]=$i
    done
    for ((j=0; j<=len2; j++)); do
        d[0,j]=$j
    done

    for ((i=1; i<=len1; i++)); do
        for ((j=1; j<=len2; j++)); do
            if [ "${str1:i-1:1}" == "${str2:j-1:1}" ]; then
                cost=0
            else
                cost=1
            fi
            d[i,j]=$((
                $((${d[i-1,j]}+1)) < $((${d[i,j-1]}+1)) ? $((${d[i-1,j]}+1)) : $((${d[i,j-1]}+1))
            ))
            d[i,j]=$((
                ${d[i,j]} < $((${d[i-1,j-1]}+cost)) ? ${d[i,j]} : $((${d[i-1,j-1]}+cost))
            ))
        done
    done

    echo ${d[len1,len2]}
}
