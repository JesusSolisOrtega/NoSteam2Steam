#!/bin/bash

# Function to select executable file
select_exe_file() {
    # Use zenity for a more touch-friendly interface on Steam Deck
    if command -v zenity >/dev/null 2>&1; then
        zenity --file-selection \
               --title="Select the game executable" \
               --file-filter="Executables | *.exe" \
               --window-icon="/usr/share/icons/steam.png"
    else
        read -p "Insert the full path to the executable (.exe): " file_path
        echo "$file_path"
    fi
}

# Function to select the correct match from the results
select_correct_match() {
    local matches="$1"
    local search_term="$2"
    local search_priority="$3"
    local options=()
    local count
    local choice
    
    # Ensure matches is valid JSON and has a .matches array
    if ! echo "$matches" | jq '.matches' >/dev/null 2>&1; then
        echo "Invalid matches data."
        return 1
    fi

    count=$(echo "$matches" | jq '.matches | length')
    
    if [ -z "$count" ] || [ "$count" -eq 0 ]; then
        echo "There is no matches to select."
        return 1
    fi
    
    # Calculate Levenshtein distance and add it to each match
    for ((i=0; i<count; i++)); do
        name=$(echo "$matches" | jq -r ".matches[$i].name")
        levenshtein_distance=$(levenshtein "$search_term" "$name")
        priority=$(echo "$search_priority" | jq -r --arg name "$name" '.[$name] // 0')
        matches=$(echo "$matches" | jq ".matches[$i] += {levenshtein: $levenshtein_distance, priority: $priority}")
    done
    
    # Sort matches by priority and then by Levenshtein distance (lower first)
    matches=$(echo "$matches" | jq '{
        matches: (.matches | sort_by(.priority, .levenshtein))
    }')
    
    # Create options for zenity with more details
    for ((i=0; i<count; i++)); do
        name=$(echo "$matches" | jq -r ".matches[$i].name")
        source=$(echo "$matches" | jq -r ".matches[$i].source")
        released=$(echo "$matches" | jq -r ".matches[$i].released")
        platforms=$(echo "$matches" | jq -r ".matches[$i].platforms | join(\", \")")
        options+=("$i" "$name ($source) - $released - $platforms")
    done
    
    # Show selection dialog with zenity
    choice=$(zenity --list \
                    --title="Select the correct game" \
                    --column="ID" --column="Game (Source) - launch Date - Platforms" \
                    "${options[@]}" \
                    --height=400 --width=600)
    
    if [ -n "$choice" ]; then
        echo "$matches" | jq ".matches[$choice]"
    else
        echo "There was not selected game."
        return 1
    fi
}
