"""Filesystem scanner, directory cache, and directory tree exploration subsystem."""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
import logging
import os
from typing import Any, Dict, List, Optional, Set

from nosteam2steam.config import ASSET_DIRS, IGNORED_DIRS
from nosteam2steam.identification.folders import (
    get_default_sync_folders,
    get_sync_folders,
)
from nosteam2steam.identification.paths import (
    generate_alternative_paths,
    is_64bit_system,
    is_steamos,
    normalize_path,
    path_exists_case_insensitive,
    select_best_path,
    sort_launch_paths,
    supports_vulkan,
)

logger = logging.getLogger(__name__)


class DirectoryCache:
    """Thread-safe in-memory cache for directory entries and explored directory trees."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, List[str]]] = {}
        self._tree_cache: Dict[str, List[Dict[str, Any]]] = {}

    def get_directory_contents(self, path: str) -> Dict[str, List[str]]:
        norm = os.path.normcase(os.path.normpath(path))
        if norm not in self._cache:
            try:
                dirs: List[str] = []
                files: List[str] = []
                with os.scandir(norm) as it:
                    for entry in it:
                        (dirs if entry.is_dir() else files).append(entry.name)
                self._cache[norm] = {"dirs": dirs, "files": files}
            except (OSError, PermissionError):
                self._cache[norm] = {"dirs": [], "files": []}
        return self._cache[norm]

    def update_directory_contents(self, path: str, contents: Dict[str, List[str]]) -> None:
        self._cache[os.path.normcase(os.path.normpath(path))] = contents

    def get_tree(self, path: str, max_depth: Optional[int]) -> Optional[List[Dict[str, Any]]]:
        key = f"{os.path.normcase(os.path.normpath(path))}:{max_depth}"
        return self._tree_cache.get(key)

    def set_tree(self, path: str, max_depth: Optional[int], items: List[Dict[str, Any]]) -> None:
        key = f"{os.path.normcase(os.path.normpath(path))}:{max_depth}"
        self._tree_cache[key] = items

    def clear(self) -> None:
        self._cache.clear()
        self._tree_cache.clear()


def process_root_folder(
    root_folder_path: str,
    root_folder: str,
    yaml_index_by_install_dir: Dict[str, Any],
    dir_cache: DirectoryCache,
) -> Dict[str, Any]:
    """Matches root directory and subdirectories against manifest install dir entries."""
    stack = [(root_folder_path, 0)]
    while stack:
        current_path, depth = stack.pop()
        if depth > 3:
            continue

        contents = dir_cache.get_directory_contents(current_path)
        current_dir = os.path.basename(current_path).lower()

        if current_dir in yaml_index_by_install_dir:
            launch_paths = yaml_index_by_install_dir[current_dir]["launch"]
            for rel in sort_launch_paths(launch_paths):
                if exe_path := select_best_path(rel.replace("<base>/", ""), current_path):
                    entry = yaml_index_by_install_dir[current_dir]
                    return {
                        root_folder: {
                            "exe_path": exe_path,
                            "game_name": entry["game_name"],
                            "steam_id": entry["steam_id"],
                            "lutris_id": entry["lutris_id"],
                            "gog_id": entry["gog_id"],
                            "files": entry["files"],
                        }
                    }

        for dir_name in reversed(contents["dirs"]):
            dir_lower = dir_name.lower()
            if (
                dir_name.startswith(".")
                or dir_lower in IGNORED_DIRS
                or dir_lower.endswith("_data")
                or dir_lower in ASSET_DIRS
            ):
                continue
            dir_path = os.path.join(current_path, dir_name)
            if os.path.islink(dir_path):
                continue
            stack.append((dir_path, depth + 1))

    return {}


def find_root_directory(
    sync_folder: str,
    yaml_index_by_install_dir: Dict[str, Any],
    dir_cache: DirectoryCache,
    excluded_folders: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Scans all subfolders in sync_folder concurrently for install directory matches."""
    excluded = excluded_folders or set()
    matches: Dict[str, Any] = {}

    try:
        with ThreadPoolExecutor() as executor:
            folders = [
                (f, os.path.join(sync_folder, f))
                for f in os.listdir(sync_folder)
                if not f.startswith(".")
                and f.lower() not in excluded
                and os.path.isdir(os.path.join(sync_folder, f))
            ]
            futures = [
                executor.submit(process_root_folder, p, f, yaml_index_by_install_dir, dir_cache) for f, p in folders
            ]
            for future in futures:
                if result := future.result():
                    matches.update(result)
    except Exception as e:
        logger.error(f"Error searching root directories: {e}")

    return matches


def explore_directory_tree(
    root_path: str,
    dir_cache: Optional[DirectoryCache] = None,
    max_depth: Optional[int] = 7,
    ignored_dirs: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Traverses root_path in breadth-first search order up to max_depth."""
    if dir_cache is not None:
        cached = dir_cache.get_tree(root_path, max_depth)
        if cached is not None:
            return cached

    results: List[Dict[str, Any]] = []
    queue: deque = deque([(root_path, 0)])
    ignored = ignored_dirs or IGNORED_DIRS

    while queue:
        current_path, depth = queue.popleft()
        if max_depth is not None and depth > max_depth:
            continue

        contents = dir_cache.get_directory_contents(current_path) if dir_cache else None
        if contents is None:
            try:
                dirs: List[str] = []
                files: List[str] = []
                with os.scandir(current_path) as it:
                    for entry in it:
                        (dirs if entry.is_dir() else files).append(entry.name)
                contents = {"dirs": dirs, "files": files}
            except (OSError, PermissionError):
                contents = {"dirs": [], "files": []}

        for file in contents["files"]:
            results.append({"path": os.path.join(current_path, file), "depth": depth, "type": "file"})

        for dir_name in contents["dirs"]:
            dir_lower = dir_name.lower()
            if (
                dir_name.startswith(".")
                or dir_lower in ignored
                or dir_lower.endswith("_data")
                or dir_lower in ASSET_DIRS
            ):
                continue
            dir_path = os.path.join(current_path, dir_name)
            if os.path.islink(dir_path):
                continue
            results.append({"path": dir_path, "depth": depth + 1, "type": "directory"})
            queue.append((dir_path, depth + 1))

    if dir_cache is not None:
        dir_cache.set_tree(root_path, max_depth, results)

    return results


__all__ = [
    "DirectoryCache",
    "explore_directory_tree",
    "find_root_directory",
    "generate_alternative_paths",
    "get_default_sync_folders",
    "get_sync_folders",
    "is_64bit_system",
    "is_steamos",
    "normalize_path",
    "path_exists_case_insensitive",
    "process_root_folder",
    "select_best_path",
    "sort_launch_paths",
    "supports_vulkan",
]
