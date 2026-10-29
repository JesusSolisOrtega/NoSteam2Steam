import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from nosteam2steam import ui
from nosteam2steam.atomic import atomic_write
from nosteam2steam.i18n import _
from nosteam2steam.config import DEFAULT_GAMES_INFO_PATH, INDEX_DIR, UNMATCHED_CANDIDATES_FILE
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


def load_unmatched_candidates() -> List[Dict[str, Any]]:
    """Loads previously discovered unmatched games catalog if available."""
    try:
        p = Path(UNMATCHED_CANDIDATES_FILE)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [c for c in data if os.path.exists(c.get("exe_path", ""))]
    except Exception as e:
        logger.debug(f"Could not load unmatched candidates: {e}")
    return []


def manual_add_game() -> bool:
    exe_file: Optional[str] = None
    candidates = load_unmatched_candidates()

    if candidates:
        menu_items = [
            (str(i + 1), f"{c['folder_name']} ({Path(c['exe_path']).name})")
            for i, c in enumerate(candidates[:15])
        ]
        menu_items.append(("manual", _("Browse for other executable...")))
        choice = ui.show_menu(
            title=_("Unidentified Games Detected"),
            text=_("The following game folders were detected but not auto-identified. Select one to register:"),
            menu_items=menu_items,
            width=600,
            height=350,
        )
        if choice and choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(candidates):
                exe_file = candidates[idx]["exe_path"]
        elif choice != "manual":
            logger.info("Manual addition aborted by user.")
            return False

    if not exe_file:
        exe_file = ui.select_path(
            title=_("Select Game Executable"), directory=False, file_filter="Executables (*.exe) | *.exe"
        )

    if not exe_file or not os.path.isfile(exe_file):
        logger.info("Manual addition cancelled or invalid file.")
        return False

    default_name = clean_executable_name(exe_file)
    user_search_term = ui.show_entry(
        title=_("Game Title"),
        text=_("Enter or confirm the title for this game:\n(Executable: {exe})", exe=Path(exe_file).name),
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
            title=_("Select Matching Game"),
            text=_("Multiple matching titles were found. Select the correct entry:"),
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

    # Remove registered candidate from unmatched catalog if present
    try:
        cand_path = Path(UNMATCHED_CANDIDATES_FILE)
        if cand_path.exists():
            with open(cand_path, "r", encoding="utf-8") as cf:
                cand_list = json.load(cf)
            if isinstance(cand_list, list):
                norm_exe = os.path.abspath(exe_file)
                updated_cand = [
                    c for c in cand_list
                    if os.path.abspath(c.get("exe_path", "")) != norm_exe
                ]
                with atomic_write(cand_path) as cf:
                    json.dump(updated_cand, cf, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"Could not update unmatched candidates catalog: {e}")

    ui.show_info(
        title=_("Game Registered"),
        text=_("'{game}' has been successfully registered in NoSteam2Steam.", game=game_name),
        width=350,
    )

    should_add_steam = ui.ask_question(
        title=_("Add to Steam"),
        text=_("Do you wish to add '{game}' to the Steam library now?", game=game_name),
        ok_label=_("Add to Steam"),
        cancel_label=_("Later"),
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
