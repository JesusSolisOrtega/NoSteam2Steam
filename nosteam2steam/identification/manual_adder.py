import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from nosteam2steam import ui
from nosteam2steam.config import DEFAULT_GAMES_INFO_PATH, INDEX_DIR
from nosteam2steam.identification.data_manager import GameDataManager
from nosteam2steam.identification.heuristics import (
    GENERIC_NAMES,
    PREFIXES,
    SUFFIXES,
    clean_executable_name,
)
from nosteam2steam.identification.lutris import (
    format_lutris_game_data,
    search_lutris_games as _lutris_search,
)
from nosteam2steam.identification.manifests import ManifestRepository

logger = logging.getLogger(__name__)


def search_lutris_games(query_name: str) -> List[Dict[str, Any]]:
    """Backward-compatible wrapper querying the Lutris search API."""
    return _lutris_search(query_name)


def manual_add_game() -> bool:
    exe_file = ui.select_path(
        title="Select Game Executable", directory=False, file_filter="Executables (*.exe) | *.exe"
    )
    if not exe_file or not os.path.isfile(exe_file):
        logger.info("Manual addition cancelled or invalid file.")
        return False

    default_name = clean_executable_name(exe_file)
    user_search_term = ui.show_entry(
        title="Game Title",
        text=f"Enter or confirm the title for this game:\n(Executable: {Path(exe_file).name})",
        default=default_name,
    )
    if not user_search_term:
        return False

    logger.info(f"Searching metadata for: {user_search_term}")
    results = search_lutris_games(user_search_term)

    chosen_game: Optional[Dict[str, Any]] = None
    if results:
        menu_items = []
        for i, item in enumerate(results[:10]):
            name = item.get("name", "Unknown")
            year = str(item.get("year", ""))
            desc = f"{year} ({item.get('slug', '')})" if year else item.get("slug", "")
            menu_items.append((str(i + 1), f"{name} - {desc}"))

        choice = ui.show_menu(
            title="Select Matching Game",
            text="Multiple matches found. Select the correct one:",
            menu_items=menu_items,
            width=550,
            height=350,
        )
        if choice and choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(results):
                chosen_game = results[idx]
        else:
            logger.info("User aborted game match selection.")
            return False

    formatted_meta = format_lutris_game_data(chosen_game, fallback_name=user_search_term)
    game_name = formatted_meta["name"]
    game_folder = Path(exe_file).parent.name

    # Look up save files metadata in local manifest repository
    files: Dict[str, Any] = {}
    try:
        repo = ManifestRepository(INDEX_DIR)
        meta = repo.get_by_name(game_name) or repo.get_by_exe(Path(exe_file).name)
        if meta and isinstance(meta.get("files"), dict):
            files = meta["files"]
    except Exception as e:
        logger.debug(f"Could not load manifest files for '{game_name}': {e}")

    new_entry = {
        game_folder: {
            **formatted_meta,
            "exe_path": os.path.abspath(exe_file),
            "files": files,
            "user_selected": True,
        }
    }

    manager = GameDataManager(str(DEFAULT_GAMES_INFO_PATH))
    manager.update_data(new_entry)
    manager.save_data()
    logger.info(f"Successfully recorded manual game entry: {game_name}")

    ui.show_info(
        title="Game Registered", text=f"'{game_name}' has been successfully registered in NoSteam2Steam.", width=350
    )

    should_add_steam = ui.ask_question(
        title="Add to Steam",
        text=f"Do you want to add '{game_name}' to your Steam library right now?",
        ok_label="Add to Steam",
        cancel_label="Later",
    )
    if should_add_steam:
        from nosteam2steam.steam import shortcuts

        shortcuts.main()

    return True


__all__ = [
    "GENERIC_NAMES",
    "PREFIXES",
    "SUFFIXES",
    "clean_executable_name",
    "manual_add_game",
    "search_lutris_games",
]


if __name__ == "__main__":
    manual_add_game()
