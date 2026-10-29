"""Fuzzy title matching and executable heuristic detection subsystem."""

import json
import logging
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from nosteam2steam.atomic import atomic_write
from nosteam2steam.config import (
    ASSET_DIRS,
    DEFAULT_SYNC_FOLDER,
    IGNORED_DIRS,
    INDEX_DIR,
    UNMATCHED_CANDIDATES_FILE,
    XML_FILE,
    YAML_FILE,
)
from nosteam2steam.identification.candidates import CandidateResolver
from nosteam2steam.identification.data_manager import GameDataManager
from nosteam2steam.identification.manifests import ManifestRepository
from nosteam2steam.identification.platform import PlatformResolver
from nosteam2steam.identification.scanner import (
    DirectoryCache,
    find_root_directory,
)

logger = logging.getLogger(__name__)


class GameMatcher:
    """Orchestrates game discovery, platform extraction, and manifest resolution."""

    def __init__(
        self,
        sync_folder: str = DEFAULT_SYNC_FOLDER,
        xml_file: str = XML_FILE,
        yaml_file: str = YAML_FILE,
        indexes: Optional[Any] = None,
        max_depth: int = 7,
    ):
        self.sync_folder = sync_folder
        self.xml_file = xml_file
        self.yaml_file = yaml_file
        self.max_depth = max_depth
        self.dir_cache = DirectoryCache()
        self.matches: Dict[str, Dict[str, Any]] = {}

        if isinstance(indexes, ManifestRepository):
            self.repository = indexes
        elif indexes is not None:
            self.repository = ManifestRepository(INDEX_DIR, preloaded=indexes)
        else:
            from nosteam2steam.identification.manifests import get_manifest_repository

            self.repository = get_manifest_repository(INDEX_DIR)
        self.platform_resolver = PlatformResolver(
            repository=self.repository,
            dir_cache=self.dir_cache,
            max_depth=self.max_depth,
        )
        self.candidate_resolver = CandidateResolver(
            repository=self.repository,
            sync_folder=self.sync_folder,
            dir_cache=self.dir_cache,
            max_depth=self.max_depth,
        )

    @property
    def indexes(self) -> ManifestRepository:
        """Exposes manifest indexes for backward-compatibility."""
        return self.repository

    def associate_exes_with_ids(self) -> Dict[str, Dict[str, Any]]:
        """Scans sync directory and maps subfolders to game metadata and executables."""
        if not os.path.exists(self.sync_folder):
            logger.error(f"Game directory '{self.sync_folder}' does not exist or cannot be accessed.")
            return {}

        data_manager = GameDataManager()
        user_selected = data_manager.get_user_selected_games()
        excluded = data_manager.get_excluded_folders(self.sync_folder, user_selected)
        excluded.update(IGNORED_DIRS)

        logger.info("Searching for matches in root directories...")
        self.matches = find_root_directory(
            sync_folder=self.sync_folder,
            yaml_index_by_install_dir=self.repository.by_install_dir,
            dir_cache=self.dir_cache,
            excluded_folders=excluded,
        )
        self.matches.update(user_selected)
        logger.info(f"Initial matches found: {len(self.matches)}")

        folders_to_process = [
            (folder, os.path.join(self.sync_folder, folder))
            for folder in os.listdir(self.sync_folder)
            if not folder.startswith(".")
            and os.path.isdir(os.path.join(self.sync_folder, folder))
            and folder not in self.matches
            and folder.lower() not in excluded
        ]

        logger.info("\nSearching for platform identifiers (Steam/GOG)...")
        with ThreadPoolExecutor() as executor:
            platform_futures = {
                executor.submit(self.platform_resolver.resolve, folder, folder_path): folder
                for folder, folder_path in folders_to_process
            }

            for future in as_completed(platform_futures):
                folder = platform_futures[future]
                try:
                    if result := future.result():
                        self.matches[folder] = result
                except Exception as e:
                    logger.error(f"Error processing platform for {folder}: {e}")

        folders_to_process = [(f, p) for f, p in folders_to_process if f not in self.matches]
        logger.info(f"Matches after platform search: {len(self.matches)}")

        logger.info("\nSearching for matches in XML/YAML...")
        with ThreadPoolExecutor() as executor:
            candidate_futures = {
                executor.submit(self.candidate_resolver.resolve, folder, folder_path): folder
                for folder, folder_path in folders_to_process
            }

            for future in as_completed(candidate_futures):
                folder = candidate_futures[future]
                try:
                    if result := future.result():
                        self.matches[folder] = result
                except Exception as e:
                    logger.error(f"Error processing candidate for {folder}: {e}")

        logger.info(f"Final matches found: {len(self.matches)}")

        unmatched = [(f, p) for f, p in folders_to_process if f not in self.matches]
        if unmatched:
            self._record_unmatched_candidates(unmatched)

        return self.matches

    def _record_unmatched_candidates(self, unmatched_folders: List[Tuple[str, str]]) -> None:
        """Records folders and executable candidates that could not be automatically matched."""
        candidates = []
        for folder, folder_path in unmatched_folders:
            exes = []
            try:
                for root, dirs, files in os.walk(folder_path):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ASSET_DIRS]
                    rel_parts = Path(root).relative_to(folder_path).parts
                    if len(rel_parts) > 3:
                        dirs.clear()
                        continue
                    for f in files:
                        if f.lower().endswith(".exe") and not any(
                            p in f.lower() for p in ["unins", "setup", "crash", "unitycrash", "redist"]
                        ):
                            exes.append(os.path.join(root, f))
            except OSError:
                pass

            if exes:
                exes.sort(key=lambda p: (len(Path(p).parts), len(Path(p).name)))
                candidates.append(
                    {
                        "folder_name": folder,
                        "folder_path": folder_path,
                        "exe_path": exes[0],
                        "all_exes": exes,
                    }
                )

        if candidates:
            try:
                with atomic_write(UNMATCHED_CANDIDATES_FILE, mode="w", encoding="utf-8") as out_file:
                    json.dump(candidates, out_file, indent=4)
                logger.info(f"Recorded {len(candidates)} unmatched candidate titles to {UNMATCHED_CANDIDATES_FILE}")
            except Exception as e:
                logger.debug(f"Could not save unmatched candidates: {e}")
