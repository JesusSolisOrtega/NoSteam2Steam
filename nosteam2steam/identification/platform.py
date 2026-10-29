"""Local platform identification detector for Steam, GOG, and emulator configurations."""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from nosteam2steam.identification.heuristics import find_best_exe_in_folder
from nosteam2steam.identification.manifests import ManifestRepository
from nosteam2steam.identification.scanner import (
    DirectoryCache,
    explore_directory_tree,
    select_best_path,
    sort_launch_paths,
)

logger = logging.getLogger(__name__)

STEAM_PATTERNS = [
    re.compile(r"appid\s*=\s*(\d{3,})", re.IGNORECASE),
    re.compile(r"#\s*appid\s*[\r\n]+\s*id\s*=\s*(\d{3,})", re.IGNORECASE),
]


class PlatformDetector:
    """Detects platform-specific metadata files (steam_appid.txt, goggame-*.info, emulator configs)."""

    @staticmethod
    def identify_platform(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Scans a file list for known platform manifests (GOG, Steam, emulators)."""
        # Pass 1: explicit known platform manifests at any depth
        for item in items:
            if item.get("type") != "file":
                continue
            path_str = str(item.get("path", ""))
            name_lower = os.path.basename(path_str).lower()

            if name_lower.startswith("goggame-") and name_lower.endswith(".info"):
                if info := PlatformDetector.handle_gog_detection(path_str, name_lower):
                    return info
            elif name_lower == "steam_appid.txt":
                if info := PlatformDetector.handle_steam_appid_detection(path_str):
                    return info

        # Pass 2: pattern detection in text/config files, restricted to shallow depths (depth <= 2)
        for item in items:
            if item.get("type") != "file" or int(item.get("depth", 0)) > 2:
                continue
            path_str = str(item.get("path", ""))
            name_lower = os.path.basename(path_str).lower()

            if name_lower.endswith((".ini", ".txt", ".cfg", ".json")):
                if info := PlatformDetector.handle_steam_pattern_detection(path_str):
                    return info
        return None

    @staticmethod
    def handle_gog_detection(file_path: str, filename: str) -> Optional[Dict[str, Any]]:
        """Extracts GOG Game ID and launch executable from goggame-*.info."""
        try:
            data = PlatformDetector.load_gog_info_file(file_path)
            if not data or not all(k in data for k in ("gameId", "rootGameId", "name")):
                return None

            if data["gameId"] != data["rootGameId"]:
                base = os.path.join(os.path.dirname(file_path), f"goggame-{data['rootGameId']}.info")
                return (
                    PlatformDetector.handle_gog_detection(base, f"goggame-{data['rootGameId']}.info")
                    if os.path.exists(base)
                    else None
                )

            exe_path = ""
            task = next((t for t in data.get("playTasks", []) if t.get("isPrimary")), None)
            if task and "path" in task:
                cand = os.path.abspath(os.path.join(os.path.dirname(file_path), task["path"]))
                if os.path.exists(cand):
                    exe_path = cand

            return {
                "platform": "gog",
                "data": {
                    "id": data["gameId"],
                    "name": str(data["name"]),
                    "path": os.path.abspath(file_path),
                    "exe_path": exe_path,
                },
            }
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return None

    @staticmethod
    def load_gog_info_file(file_path: str) -> Optional[Dict[str, Any]]:
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return json.load(f)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        return None

    @staticmethod
    def handle_steam_appid_detection(file_path: str) -> Optional[Dict[str, Any]]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                if (appid := f.read().strip()).isdigit():
                    return {"platform": "steam", "data": {"appid": appid, "source_file": file_path}}
        except (IOError, UnicodeDecodeError) as e:
            logger.error(f"Error reading {file_path}: {e}")
        return None

    @staticmethod
    def handle_steam_pattern_detection(file_path: str) -> Optional[Dict[str, Any]]:
        try:
            content = ""
            for enc in ("utf-8", "latin-1"):
                try:
                    with open(file_path, "r", encoding=enc) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            if file_path.lower().endswith(".json"):
                try:
                    if appid := PlatformDetector.find_appid_in_json(json.loads(content)):
                        return {"platform": "steam", "data": {"appid": appid, "source_file": file_path}}
                except json.JSONDecodeError:
                    pass

            for pattern in STEAM_PATTERNS:
                if match := pattern.search(content):
                    return {"platform": "steam", "data": {"appid": match.group(1), "source_file": file_path}}
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
        return None

    @staticmethod
    def find_appid_in_json(obj: Any) -> Optional[str]:
        if isinstance(obj, dict):
            if "appid" in obj:
                val = str(obj["appid"]).split(".")[0].strip()
                if val.isdigit() and len(val) >= 3:
                    return val
            for v in obj.values():
                if res := PlatformDetector.find_appid_in_json(v):
                    return res
        elif isinstance(obj, list):
            for item in obj:
                if res := PlatformDetector.find_appid_in_json(item):
                    return res
        return None


class PlatformResolver:
    """Resolves local platform manifests (Steam appid, GOG info) to catalog metadata and executables."""

    def __init__(
        self,
        repository: ManifestRepository,
        dir_cache: Optional[DirectoryCache] = None,
        max_depth: int = 7,
    ):
        self.repository = repository
        self.dir_cache = dir_cache
        self.max_depth = max_depth

    def _fast_probe(self, folder_name: str, folder_path: str) -> Optional[Dict[str, Any]]:
        """Quickly probes root folder (depth 0) for platform files without full recursion."""
        try:
            entries = os.listdir(folder_path)
        except OSError:
            return None

        # 1. GOG manifest in root
        for entry in entries:
            name_lower = entry.lower()
            if name_lower.startswith("goggame-") and name_lower.endswith(".info"):
                gog_path = os.path.join(folder_path, entry)
                if info := PlatformDetector.handle_gog_detection(gog_path, name_lower):
                    data = info["data"]
                    gog_id = data.get("id", "")
                    raw_name = data.get("name", folder_name)
                    meta = self.repository.get_by_gog_id(gog_id) if gog_id else None
                    game_name = (meta.get("game_name") if meta else None) or raw_name
                    known_exe = data.get("exe_path", "")
                    if known_exe and os.path.exists(known_exe):
                        return {
                            "exe_path": known_exe,
                            "game_name": game_name,
                            "steam_id": meta.get("steam_id", "") if meta else "",
                            "lutris_id": meta.get("lutris_id", "") if meta else "",
                            "gog_id": gog_id,
                            "files": meta.get("files", {}) if meta else {},
                        }

        # 2. Steam AppID in root
        for entry in entries:
            if entry.lower() == "steam_appid.txt":
                appid_path = os.path.join(folder_path, entry)
                if info := PlatformDetector.handle_steam_appid_detection(appid_path):
                    steam_id = info["data"]["appid"]
                    meta = self.repository.get_by_steam_id(steam_id)
                    game_name = (meta.get("game_name") if meta else None) or folder_name
                    if meta and "launch" in meta:
                        for rel in sort_launch_paths(meta["launch"]):
                            if cand := select_best_path(rel.replace("<base>/", ""), folder_path):
                                return {
                                    "exe_path": cand,
                                    "game_name": game_name,
                                    "steam_id": steam_id,
                                    "lutris_id": meta.get("lutris_id", "") if meta else "",
                                    "gog_id": meta.get("gog_id", "") if meta else "",
                                    "files": meta.get("files", {}) if meta else {},
                                }
                    best = find_best_exe_in_folder(folder_path, reference_name=game_name, search_subdirs=False)
                    if best:
                        return {
                            "exe_path": best,
                            "game_name": game_name,
                            "steam_id": steam_id,
                            "lutris_id": meta.get("lutris_id", "") if meta else "",
                            "gog_id": meta.get("gog_id", "") if meta else "",
                            "files": meta.get("files", {}) if meta else {},
                        }

        return None

    def resolve(
        self,
        folder_name: str,
        folder_path: str,
        items: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        if items is None:
            if fast_match := self._fast_probe(folder_name, folder_path):
                return fast_match
            items = explore_directory_tree(folder_path, dir_cache=self.dir_cache, max_depth=self.max_depth)

        info = PlatformDetector.identify_platform(items)
        if not info:
            return None

        platform, data = info["platform"], info["data"]
        steam_id = data.get("appid", "") if platform == "steam" else ""
        gog_id = data.get("id", "") if platform == "gog" else ""
        raw_name = data.get("name", os.path.basename(folder_path))

        meta = (
            self.repository.get_by_steam_id(steam_id)
            if steam_id
            else self.repository.get_by_gog_id(gog_id)
            if gog_id
            else None
        )

        game_name = (meta.get("game_name") if meta else None) or raw_name
        exe_path = self._resolve_binary(
            folder_path, meta, game_name, data.get("exe_path", ""), items, search_subdirs=(platform == "steam")
        )

        if not exe_path:
            return None

        return {
            "exe_path": exe_path,
            "game_name": game_name,
            "steam_id": steam_id or (meta.get("steam_id", "") if meta else ""),
            "lutris_id": meta.get("lutris_id", "") if meta else "",
            "gog_id": gog_id or (meta.get("gog_id", "") if meta else ""),
            "files": meta.get("files", {}) if meta else {},
        }

    def _resolve_binary(
        self,
        folder_path: str,
        meta: Optional[Dict[str, Any]],
        game_name: str,
        known_exe: str,
        items: List[Dict[str, Any]],
        search_subdirs: bool,
    ) -> Optional[str]:
        if known_exe and os.path.exists(known_exe):
            return known_exe

        if meta and "launch" in meta:
            for rel in sort_launch_paths(meta["launch"]):
                if candidate := select_best_path(rel.replace("<base>/", ""), folder_path):
                    return candidate

        return find_best_exe_in_folder(
            folder_path, reference_name=game_name, search_subdirs=search_subdirs, items_to_search=items
        )
