import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, Set

from nosteam2steam.config import DEFAULT_GAMES_INFO_PATH
from nosteam2steam.identification.lutris import LutrisDataEnhancer

logger = logging.getLogger(__name__)


class GameDataManager:
    def __init__(self, json_path: str = str(DEFAULT_GAMES_INFO_PATH)):
        self.json_path = Path(json_path)
        self.data = self._load_existing_data()
        self.lock = threading.Lock()

    def _load_existing_data(self) -> Dict[str, Any]:
        if self.json_path.exists():
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading file {self.json_path}: {str(e)}")
                return {}
        return {}

    def _merge_game_data(self, existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        if not existing:
            return new.copy()
        if not new:
            return existing.copy()

        merged = existing.copy()

        simple_fields = [
            "name",
            "slug",
            "source",
            "released",
            "background_image",
            "rating",
            "metacritic",
            "banner_url",
            "icon_url",
            "coverart",
            "exe_path",
            "user_selected",
        ]
        for field in simple_fields:
            if field in new and (field not in merged or not merged[field]):
                merged[field] = new[field]

        if "platforms" in new:
            existing_platforms = set(existing.get("platforms", []))
            new_platforms = set(new.get("platforms", []))
            merged["platforms"] = list(existing_platforms.union(new_platforms))

        if "providers" in new:
            existing_providers = {tuple(sorted(d.items())) for d in existing.get("providers", [])}
            new_providers = {tuple(sorted(d.items())) for d in new.get("providers", [])}
            merged["providers"] = [dict(p) for p in existing_providers.union(new_providers)]

        return merged

    def update_data(self, new_data: Dict[str, Dict[str, Any]]) -> None:
        with self.lock:
            for game_key, game_data in new_data.items():
                if game_key in self.data:
                    prev_exe = self.data[game_key].get("exe_path")
                    new_exe = game_data.get("exe_path")
                    if prev_exe and new_exe and prev_exe != new_exe:
                        self.data[game_key] = game_data
                    else:
                        self.data[game_key] = self._merge_game_data(self.data[game_key], game_data)
                else:
                    self.data[game_key] = game_data

    def save_data(self) -> None:
        temp_path = self.json_path.with_suffix(".tmp")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

            temp_path.replace(self.json_path)
            logger.info(f"Data successfully saved to {self.json_path}")
        except IOError as e:
            logger.error(f"Error saving data: {str(e)}")
            if temp_path.exists():
                temp_path.unlink()

    def get_current_data(self) -> Dict[str, Any]:
        with self.lock:
            return self.data.copy()

    def get_user_selected_games(self) -> Dict[str, Dict[str, Any]]:
        """Returns games explicitly confirmed by user in games.json."""
        with self.lock:
            return {folder: data for folder, data in self.data.items() if data.get("user_selected") is True}

    @staticmethod
    def get_excluded_folders(sync_folder: str, user_selected_games: Dict[str, Dict[str, Any]]) -> Set[str]:
        """Calculates top-level subfolders to skip during automated scan."""
        excluded: Set[str] = set()
        sync_folder_normalized = os.path.normcase(os.path.normpath(sync_folder))

        for data in user_selected_games.values():
            if "exe_path" in data:
                exe_path = os.path.normcase(os.path.normpath(data["exe_path"]))
                if exe_path.startswith(sync_folder_normalized):
                    rel_path = os.path.relpath(os.path.dirname(exe_path), sync_folder_normalized)
                    if os.sep not in rel_path:
                        continue
                    top_subfolder = rel_path.split(os.sep)[0]
                    excluded.add(top_subfolder.lower())

        return excluded


def load_user_selected_games(
    games_json_path: str = DEFAULT_GAMES_INFO_PATH,
) -> Dict[str, Dict[str, Any]]:
    """Convenience helper to retrieve confirmed games from JSON path."""
    return GameDataManager(games_json_path).get_user_selected_games()


def get_excluded_folders(sync_folder: str, user_selected_games: Dict[str, Dict[str, Any]]) -> Set[str]:
    """Convenience helper to compute excluded subfolders."""
    return GameDataManager.get_excluded_folders(sync_folder, user_selected_games)


def main():
    from nosteam2steam.identification.identifier import run_identification
    from nosteam2steam import ui
    from nosteam2steam.i18n import _

    with ui.progress_dialog("NoSteam2Steam", _("Searching for games on the system...")) as progress:
        start_time = time.time()

        logger.info("Retrieving initial data...")
        progress.update(_("Identifying installed titles..."))
        associate_data = run_identification()

        manager = GameDataManager()
        existing_data = manager.data

        to_enhance = {}
        cached_enhanced = {}
        for folder, gdata in associate_data.items():
            gname = gdata.get("game_name", "")
            existing_entry = existing_data.get(folder) or next(
                (v for v in existing_data.values() if v.get("name") == gname), None
            )
            if (
                existing_entry
                and existing_entry.get("banner_url")
                and existing_entry.get("coverart")
                and existing_entry.get("providers")
            ):
                merged = existing_entry.copy()
                merged["exe_path"] = gdata.get("exe_path", merged.get("exe_path", ""))
                merged["files"] = gdata.get("files", merged.get("files", {}))
                cached_enhanced[folder] = merged
            else:
                to_enhance[folder] = gdata

        if to_enhance:
            logger.info(f"Enhancing {len(to_enhance)} new/unindexed games with Lutris information...")
            progress.update(_("Consulting catalog and metadata..."))
            enhancer = LutrisDataEnhancer(to_enhance)
            newly_enhanced = enhancer.enhance_with_lutris_data()
            cached_enhanced.update(newly_enhanced)
        else:
            logger.info("All discovered games already possess complete cached metadata.")

        logger.info("Updating database...")
        progress.update(_("Saving game catalog..."))
        manager.update_data(cached_enhanced)
        manager.save_data()

        elapsed = time.time() - start_time
        logger.info(f"Process completed in {elapsed:.2f} seconds")
        logger.info(f"Total games processed: {len(cached_enhanced)}")
        return {"identified": len(cached_enhanced)}


if __name__ == "__main__":
    main()
