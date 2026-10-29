"""Steam library integration and shortcut management."""

import os
import json
import logging
import sys
from typing import Dict, Any, Tuple, Union, Optional, Callable

from nosteam2steam import ui
from nosteam2steam.utils import ensure_steam_closed
from nosteam2steam.steam.vdf_binary import (
    load_shortcuts,
    save_shortcuts,
    get_valid_shortcuts,
    reindex_shortcuts_alphabetically,
)
from nosteam2steam.steam.grid import save_grid_images
from nosteam2steam.steam.compat import set_proton_compat_tools

from nosteam2steam.config import (
    DEFAULT_GAMES_INFO_PATH,
    STEAM_ID_MAPPING_FILE,
    USER_MAPPING_PATH,
)
from nosteam2steam.steam.ids import (
    generate_app_id,
    generate_short_app_id,
    generate_shortcut_id,
)
from nosteam2steam.steam.environment import (
    SHORTCUTS_FILE,
    STEAM_USERDATA_DIR,
    get_current_user,
    get_proton_version,
)

logger = logging.getLogger(__name__)


def save_steam_id_mapping(steam_id_mapping: Dict[str, Any]) -> None:
    try:
        existing_mapping = {}
        if os.path.exists(STEAM_ID_MAPPING_FILE):
            with open(STEAM_ID_MAPPING_FILE, "r") as f:
                existing_mapping = json.load(f)

        if steam_id_mapping:
            existing_mapping.update(steam_id_mapping)

            with open(STEAM_ID_MAPPING_FILE, "w") as f:
                json.dump(existing_mapping, f, indent=4)

            logger.info("Game-steam_id mapping updated in steam_id_mapping.json")
        else:
            logger.info("No new games found to update.")
    except Exception as e:
        logger.error(f"Error saving game-steam_id mapping: {e}")


def process_user_selected_games(json_file: str) -> None:
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            games_data = json.load(f)

        needs_processing = any(game.get("user_selected", False) and "files" not in game for game in games_data.values())

        if needs_processing:
            from nosteam2steam.identification.identifier import add_files_to_user_selected

            logger.info("Processing user-selected games...")
            games_data = add_files_to_user_selected(games_data)

            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(games_data, f, indent=4)
            logger.info("Updated games.json with user-selected games files.")

    except Exception as e:
        logger.error(f"Error processing user-selected games: {e}")


def load_games(json_file: str) -> Dict[str, Any]:
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            games = json.load(f)

        for game in games.values():
            if "exe_path" in game:
                game["exe_path"] = os.path.expanduser(game["exe_path"])

        return {key: value for key, value in games.items() if os.path.exists(value.get("exe_path", ""))}
    except Exception as e:
        logger.error(f"Error loading {json_file}: {e}")
        return {}


def save_user_mapping(user_mapping: Dict[str, Any]) -> None:
    try:
        with open(USER_MAPPING_PATH, "w") as f:
            json.dump(user_mapping, f, indent=4)
        logger.info(f"User mapping saved to {USER_MAPPING_PATH}")
    except Exception as e:
        logger.error(f"Error saving user mapping: {e}")


def game_exists(shortcuts_source: Union[str, Dict[str, Any]], exe_path: str, game_name: str) -> bool:
    try:
        if isinstance(shortcuts_source, dict):
            shortcuts = shortcuts_source
        elif isinstance(shortcuts_source, str):
            if not os.path.exists(shortcuts_source):
                return False
            shortcuts = load_shortcuts(shortcuts_source)
        else:
            return False

        norm_exe = os.path.normcase(os.path.normpath(exe_path))
        for shortcut in shortcuts.values():
            shortcut_exe = shortcut.get("Exe", "").strip('"')
            shortcut_name = shortcut.get("appname", "")
            if (
                os.path.normcase(os.path.normpath(shortcut_exe)) == norm_exe
                and shortcut_name == game_name
            ):
                return True
        return False
    except Exception as e:
        logger.error(f"Error checking game existence in shortcuts: {e}")
        return False


def find_entry_index(shortcuts: Dict[str, Any]) -> Tuple[str, int]:
    if not shortcuts:
        return "0", 0
    entry_index = max(int(key) for key in shortcuts.keys()) + 1
    return str(entry_index), entry_index


def add_entry(shortcuts: Dict[str, Any], input_tuple: Tuple) -> None:
    entry_id = input_tuple[13][0]
    shortcuts[entry_id] = {
        "appid": int(input_tuple[0]),
        "appname": input_tuple[1],
        "Exe": input_tuple[2],
        "StartDir": input_tuple[3],
        "icon": input_tuple[4],
        "ShortcutPath": input_tuple[5],
        "LaunchOptions": input_tuple[6],
        "IsHidden": int(input_tuple[7]),
        "AllowDesktopConfig": int(input_tuple[8]),
        "AllowOverlay": int(input_tuple[9]),
        "OpenVR": int(input_tuple[10]),
        "Devkit": int(input_tuple[11]),
        "DevkitGameID": input_tuple[12],
        "DevkitOverrideAppID": 0,
        "LastPlayTime": 0,
        "FlatpakAppID": "",
        "tags": {},
    }


def input_preparation(args: Tuple, entry_index: Tuple[str, int]) -> Tuple:
    var_appid = args[0]
    var_app_name = args[1]
    var_path = f'"{args[2]}"'
    var_start_dir = f'"{args[3]}"'
    var_icon_path = args[4]
    var_shortcut_path = args[5]
    var_launch_options = args[6]
    var_is_hidden = args[7]
    var_allow_desktop_config = args[8]
    var_allow_overlay = args[9]
    var_open_vr = args[10]
    var_devkit = args[11]
    var_devkit_game_id = args[12]

    return (
        var_appid,
        var_app_name,
        var_path,
        var_start_dir,
        var_icon_path,
        var_shortcut_path,
        var_launch_options,
        var_is_hidden,
        var_allow_desktop_config,
        var_allow_overlay,
        var_open_vr,
        var_devkit,
        var_devkit_game_id,
        entry_index,
    )


def add_games_to_shortcuts(
    games: Dict[str, Any], user_id: str, progress_callback: Optional[Callable[[str], None]] = None
) -> Tuple[Dict[str, Any], int, int]:
    user_config_dir = os.path.join(STEAM_USERDATA_DIR, user_id, "config")
    shortcuts_path = os.path.join(user_config_dir, SHORTCUTS_FILE)

    valid_shortcuts, removed_count = get_valid_shortcuts(shortcuts_path)
    shortcuts = reindex_shortcuts_alphabetically(valid_shortcuts)

    steam_id_mapping = {}
    games_added = 0
    games_updated = 0
    proton_version = get_proton_version()
    compat_tools_to_set: Dict[str, str] = {}

    try:
        total = len(games)
        for idx, (game_folder, game_data) in enumerate(games.items(), 1):
            exe_path = game_data.get("exe_path", "")
            if not os.path.exists(exe_path):
                continue

            game_name = game_data["name"]
            if progress_callback:
                progress_callback(f"Configurando arte y acceso directo ({idx}/{total}): {game_name}")

            steam_app_id = next((p["id"] for p in game_data.get("providers", []) if p["service"] == "steam"), None)
            app_id_long = generate_app_id(game_data["exe_path"], game_name)
            app_id_short = generate_short_app_id(game_data["exe_path"], game_name)
            shortcut_id = generate_shortcut_id(game_data["exe_path"], game_name)

            steam_id_mapping[game_name] = {
                "app_id_long": app_id_long,
                "app_id_short": app_id_short,
                "shortcut_id": shortcut_id,
                "exe_path": game_data["exe_path"],
                "files": game_data.get("files", []),
                "install_dir": game_folder,
                "steam_app_id": steam_app_id,
            }

            image_updated = save_grid_images(app_id_short, user_config_dir, game_data, app_id_long, exe_path)
            if image_updated:
                games_updated += 1

            if game_exists(shortcuts, game_data["exe_path"], game_name):
                continue

            entry_index = find_entry_index(shortcuts)

            icon_name = f"{app_id_short}.ico"
            icon_path = os.path.join(user_config_dir, "icons", icon_name)
            if not os.path.exists(icon_path):
                icon_name = f"{app_id_short}.png"
                icon_path = os.path.join(user_config_dir, "icons", icon_name)

            game_data["icon"] = icon_path

            input_tuple = input_preparation(
                (
                    shortcut_id,
                    game_data["name"],
                    game_data["exe_path"],
                    os.path.dirname(game_data["exe_path"]),
                    game_data["icon"],
                    "",
                    "",
                    "1",
                    "1",
                    "0",
                    "0",
                    "0",
                ),
                entry_index,
            )
            add_entry(shortcuts, input_tuple)

            games_added += 1

            if proton_version:
                compat_tools_to_set[app_id_short] = proton_version

        if compat_tools_to_set:
            set_proton_compat_tools(compat_tools_to_set)

        save_shortcuts(shortcuts_path, shortcuts)

        logger.info(f"Summary: {games_added} games added, {games_updated} games updated, {removed_count} games removed")
    except Exception as e:
        logger.error(f"Error processing shortcuts.vdf file: {e}")
        sys.exit(1)

    return steam_id_mapping, games_added, games_updated


def _add_games_to_steam(json_file: str = DEFAULT_GAMES_INFO_PATH) -> Dict[str, Any]:
    logger.info("Starting script...")

    if not os.path.exists(json_file):
        logger.error(f"JSON file does not exist: {json_file}")
        sys.exit(1)

    process_user_selected_games(json_file)

    games = load_games(json_file)
    logger.info(f"Loaded {len(games)} games from JSON file.")

    selected_user = get_current_user()
    if not selected_user:
        logger.error("Could not find an active Steam user.")
        ui.show_error(
            title="Steam User Not Found",
            text="Could not determine active Steam user.\nPlease ensure Steam has been launched and logged in at least once.",
            width=350,
        )
        return {"added": 0, "updated": 0, "total": 0}

    if selected_user == "all":
        user_folders = [
            f for f in os.listdir(STEAM_USERDATA_DIR) if os.path.isdir(os.path.join(STEAM_USERDATA_DIR, f)) and f != "0"
        ]
    else:
        user_folders = [selected_user]

    steam_id_mapping = {}
    total_added = 0
    total_updated = 0

    with ui.progress_dialog("NoSteam2Steam", "Preparando accesos directos de Steam...") as progress:
        for user_id in user_folders:
            logger.info(f"Processing user: {user_id}")
            user_steam_id_mapping, added, updated = add_games_to_shortcuts(
                games, user_id, progress_callback=lambda msg: progress.update(msg)
            )
            steam_id_mapping.update(user_steam_id_mapping)
            total_added += added
            total_updated += updated

        progress.update("Guardando catálogo de accesos directos...")
        save_steam_id_mapping(steam_id_mapping)

    logger.info("Script finished successfully.")
    return {"added": total_added, "updated": total_updated, "total": len(games)}


def main(json_file: str = DEFAULT_GAMES_INFO_PATH) -> Dict[str, Any]:
    ensure_steam_closed()
    return _add_games_to_steam(json_file)


if __name__ == "__main__":
    target_json = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GAMES_INFO_PATH
    if not os.path.exists(target_json):
        logger.error(f"JSON file does not exist: {target_json}")
        sys.exit(1)
    main(target_json)
