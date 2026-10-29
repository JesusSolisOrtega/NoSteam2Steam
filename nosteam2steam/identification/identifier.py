"""Game identification orchestration module."""

import logging
import time
from typing import Any, Dict, Optional, Union

from nosteam2steam.config import (
    DEFAULT_SYNC_FOLDER,
    XML_FILE,
    YAML_FILE,
)
from nosteam2steam.identification.manifests import verify_and_download_files, get_manifest_repository, ManifestRepository
from nosteam2steam.identification.matcher import GameMatcher
from nosteam2steam.identification.scanner import get_sync_folders

logger = logging.getLogger(__name__)


def associate_exes_with_ids(
    sync_folder: str = DEFAULT_SYNC_FOLDER,
    xml_file: str = XML_FILE,
    yaml_file: str = YAML_FILE,
    indexes: Optional[Union[Dict[str, Any], ManifestRepository]] = None,
    max_depth: int = 7,
) -> Dict[str, Dict]:
    matcher = GameMatcher(sync_folder, xml_file, yaml_file, indexes, max_depth)
    return matcher.associate_exes_with_ids()


def run_identification() -> Dict[str, Any]:
    verify_and_download_files()
    repo = get_manifest_repository()
    sync_folders = get_sync_folders()
    max_depth = 8

    all_matches = {}
    for folder in sync_folders:
        logger.info(f"\nProcessing folder: {folder}")
        matches = associate_exes_with_ids(folder, XML_FILE, YAML_FILE, indexes=repo, max_depth=max_depth)
        all_matches.update(matches)

    return all_matches


def add_files_to_user_selected(games_data: dict, matcher: Optional[GameMatcher] = None) -> dict:
    if matcher is None:
        indexes = verify_and_download_files()
        yaml_by_name = indexes.get("yaml", {}).get("by_name", {})
    else:
        yaml_by_name = matcher.indexes.get("yaml_by_name", {})

    for game_name, game_info in games_data.items():
        if game_info.get("user_selected") and "files" not in game_info:
            yaml_entry = yaml_by_name.get(game_info.get("name", "").lower())
            if isinstance(yaml_entry, dict):
                game_info["files"] = yaml_entry.get("files", {})

    return games_data


def main() -> None:
    start_time = time.perf_counter()
    logger.info("Starting Game identification process...")
    matches = run_identification()

    logger.info("\nResults:")
    for folder, data in matches.items():
        logger.info(f"\nFolder: {folder}")
        logger.info(f"  EXE found: {data['exe_path']}")
        logger.info(f"  Game: {data['game_name']}")
        if data.get("steam_id"):
            logger.info(f"  SteamID: {data['steam_id']}")
        if data.get("lutris_id"):
            logger.info(f"  LutrisID: {data['lutris_id']}")
        if data.get("gog_id"):
            logger.info(f"  GOGID: {data['gog_id']}")

    elapsed = time.perf_counter() - start_time
    if elapsed > 60:
        minutes = int(elapsed // 60)
        seconds = elapsed % 60
        time_str = f"{minutes} minutes and {seconds:.2f} seconds"
    else:
        time_str = f"{elapsed:.2f} seconds"

    logger.info(f"\nFinished. Total time: {time_str}")


__all__ = [
    "GameMatcher",
    "associate_exes_with_ids",
    "run_identification",
    "add_files_to_user_selected",
    "main",
]

if __name__ == "__main__":
    main()
