#!/bin/bash

select_search_mode() {
    if command -v zenity >/dev/null 2>&1; then
        search_mode=$(zenity --list \
                             --title="Search Mode" \
                             --column="Mode" \
                             "Automatic" "Manual" \
                             --height=200 --width=300)
        if [ -z "$search_mode" ]; then
            echo "Aborted by the user."
            exit 0
        fi
    else
        echo "Select search mode:"
        echo "1. Automatic"
        echo "2. Manual"
        read -p "Option: " search_mode
        if [ "$search_mode" == "1" ]; then
            search_mode="Automatic"
        else
            search_mode="Manual"
        fi
    fi
    echo "$search_mode"
}

handle_automatic_search() {
    local exe_path="$1"
    local games_data="$2"
    updated_data=$(detect_game_from_exe "$exe_path" "$games_data")
    if [ $? -eq 0 ]; then
        echo "$updated_data" | jq '.'
        save_games_data "$updated_data"
        return 0
    fi
    return 1
}

handle_manual_search() {
    local exe_path="$1"
    local games_data="$2"
    if command -v zenity >/dev/null 2>&1; then
        game_name=$(zenity --entry --title="Type the game name" --text="Type the game name:")
        if [ -z "$game_name" ]; then
            echo "Aborted by the user."
            exit 0
        fi
    else
        read -p "Type the game name: " game_name
    fi

    updated_data=$(detect_game_from_exe "$exe_path" "$games_data" "$game_name")
    if [ $? -eq 0 ]; then
        echo "$updated_data" | jq '.'
        save_games_data "$updated_data"
        return 0
    fi
    return 1
}

prompt_retry() {
    while true; do
        read -p "¿Do you want to try with another name? (S/n): " yn
        yn=${yn:-S}
        case $yn in
            [Ss]* ) return 0;;
            [Nn]* ) echo "Aborted by the user."; exit 0;;
            * ) echo "Please type S o n.";;
        esac
    done
}
