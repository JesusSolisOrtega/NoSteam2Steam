#!/bin/bash

# Function to clean the name of the executable
clean_exe_name() {
    local exe_name="$1"
    
    local prefixes=("Launcher_" "Game_" "Steam_" "Uplay_" "Epic_" "GOG_" "Retail_" "Demo_")
    local suffixes=("_Launcher.exe" "_Game.exe" "_Win.exe" "_64.exe" "_x64.exe" "_32.exe" "_x86.exe" "_Main.exe" "_Shipping.exe" "_Final.exe" "_Beta.exe" "_Test.exe" "_Trial.exe" "_DX11.exe" "_DX12.exe" "_VR.exe")
    
    for prefix in "${prefixes[@]}"; do
        exe_name="${exe_name#"$prefix"}"
    done
    
    for suffix in "${suffixes[@]}"; do
        exe_name="${exe_name%"$suffix"}"
    done
    
    echo "$exe_name"
}

# Function to generate a slug from a given string
generate_slug() {
    local name="$1"
    echo "$name" | iconv -t ascii//TRANSLIT | tr -cd '[:alnum:]' | tr '[:upper:]' '[:lower:]' | sed -e 's/[^a-z0-9]/-/g' -e 's/--*/-/g' -e 's/^-//' -e 's/-$//'
}

extract_slug() {
    local exe_name="$1"
    exe_name=$(clean_exe_name "$exe_name")
    local slug

    # Manejar números romanos (I, V, X) al final del nombre
    if [[ "$exe_name" =~ (I|V|X)+$ ]]; then
        local roman_part="${BASH_REMATCH[0]}"
        local base_name="${exe_name%$roman_part}"
        slug=$(echo "$base_name" | sed -E 's/([a-zA-Z])([A-Z])/\1-\2/g')
        slug="${slug}-${roman_part,,}"  # Convertir números romanos a minúsculas
    else
        # Insertar guiones antes de mayúsculas no iniciales
        slug=$(echo "$exe_name" | sed -E 's/([a-zA-Z])([A-Z])/\1-\2/g')
    fi

    # Convertir a minúsculas y normalizar
    slug=$(echo "$slug" | tr '[:upper:]' '[:lower:]' | tr -c '[:alnum:]\n' '-' | tr -s '-' | sed -E 's/^-|-$//g')

    echo "$slug"
}

extract_slug_without_hyphens() {
    local exe_name="$1"
    exe_name=$(clean_exe_name "$exe_name")
    local slug

    # Normalizar espacios, guiones bajos y caracteres especiales
    slug=$(echo "$exe_name" | tr '_' ' ' | tr -c '[:alnum:]\n' ' ')

    # Convertir a minúsculas y eliminar puntuación
    slug=$(echo "$slug" | tr '[:upper:]' '[:lower:]' | tr -d '[:punct:]' | tr ' ' '-' | tr -s '-')

    # Eliminar guiones dobles y guiones al inicio/final
    slug=$(echo "$slug" | sed -E 's/--+/-/g' | sed -E 's/^-|-$//g')

    echo "$slug"
}

try_different_slugs() {
    local exe_name="$1"
    local combined_results='{"matches": []}'
    local slug_functions=("extract_slug" "extract_slug_without_hyphens")
    local slugs=()

    # Generar todos los slugs primero
    for slug_function in "${slug_functions[@]}"; do
        local slug=$($slug_function "$exe_name")
        log_data "Slug generado ($slug_function): $slug"
        slugs+=("$slug")
    done

    # Usar los slugs generados en la búsqueda
    for slug in "${slugs[@]}"; do
        combined_results=$(search_game "$slug")
        if [ "$(echo "$combined_results" | jq '.matches | length')" -gt 0 ]; then
            echo "$combined_results"
            return 0
        fi
    done

    # Si no se encontraron resultados, intentar sin números romanos o normales
    if [[ "$exe_name" =~ (I|V|X)+$ || "$exe_name" =~ [0-9]+$ ]]; then
        local base_name="${exe_name%${BASH_REMATCH[0]}}"
        for slug_function in "${slug_functions[@]}"; do
            local slug_without_number=$($slug_function "$base_name")
            log_data "Slug sin número ($slug_function): $slug_without_number"
            combined_results=$(search_game "$slug_without_number")
            if [ "$(echo "$combined_results" | jq '.matches | length')" -gt 0 ]; then
                echo "$combined_results"
                return 0
            fi
        done
    fi

    echo "$combined_results"
    return 1
}