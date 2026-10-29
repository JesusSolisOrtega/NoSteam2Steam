"""Manifest cascade and heuristic candidate resolution subsystem."""

import logging
import os
from typing import Any, Dict, List, Optional

from nosteam2steam.config import GENERIC_EXECUTABLE_STEMS, IGNORED_FILES
from nosteam2steam.identification.heuristics import clean_executable_name, simple_match_score
from nosteam2steam.identification.manifests import ManifestRepository
from nosteam2steam.identification.scanner import (
    DirectoryCache,
    explore_directory_tree,
    is_64bit_system,
    normalize_path,
)

logger = logging.getLogger(__name__)


class CandidateResolver:
    """Evaluates filesystem structures against manifests via XML, YAML, JRE, and fuzzy heuristics."""

    def __init__(
        self,
        repository: ManifestRepository,
        sync_folder: str,
        dir_cache: Optional[DirectoryCache] = None,
        max_depth: int = 7,
    ):
        self.repository = repository
        self.sync_folder = sync_folder
        self.dir_cache = dir_cache
        self.max_depth = max_depth

    def _fast_probe(self, folder_name: str, folder_path: str) -> Optional[Dict[str, Any]]:
        """Quickly checks root folder (depth 0) for direct XML/YAML executable matches."""
        try:
            entries = os.listdir(folder_path)
        except OSError:
            return None

        root_items: List[Dict[str, Any]] = []
        for f in entries:
            stem, ext = os.path.splitext(f)
            if ext.lower() == ".exe" and stem.lower() not in IGNORED_FILES:
                full_path = os.path.join(folder_path, f)
                if os.path.isfile(full_path):
                    root_items.append({"path": full_path, "depth": 0, "type": "file"})

        if not root_items:
            return None

        exes, _ = self._filter_items(root_items)
        if not exes:
            return None

        # Exclude generic executable stems from fast-probe direct matching
        # to prevent generic names (e.g. Game.exe) from false-matching random catalog entries
        specific_exes = [e for e in exes if e["stem_lower"] not in GENERIC_EXECUTABLE_STEMS]
        if not specific_exes:
            return None

        if match := self._match_xml(specific_exes, folder_name=folder_name):
            return match
        if match := self._match_yaml_direct(specific_exes, folder_name=folder_name):
            return match

        return None

    def resolve(
        self,
        folder_name: str,
        folder_path: str,
        items: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolves root folder through manifest and heuristic matching cascade."""
        try:
            if items is None:
                if fast_match := self._fast_probe(folder_name, folder_path):
                    return fast_match
                items = explore_directory_tree(folder_path, dir_cache=self.dir_cache, max_depth=self.max_depth)

            exes, jre_paths = self._filter_items(items)
            if not exes and not jre_paths["jre"] and not jre_paths["jre_x64"]:
                return None

            # 1. XML manifest candidates
            if match := self._match_xml(exes, folder_name=folder_name):
                return match

            # 2. Direct YAML match (prioritizing shallower depths)
            if match := self._match_yaml_direct(exes, folder_name=folder_name):
                return match

            # 3. Java runtime match
            if match := self._match_java(jre_paths):
                return match

            # 4. Fuzzy lexical matching
            return self._match_fuzzy(folder_name, exes)

        except Exception as e:
            logger.error(f"Error resolving candidates for {folder_name}: {e}")
            return None

    def _filter_items(self, items: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, Optional[str]]]:
        exes: List[Dict[str, Any]] = []
        jre: Dict[str, Optional[str]] = {"jre": None, "jre_x64": None}

        for item in items:
            itype = item.get("type")
            path_str = str(item.get("path", ""))

            if itype == "file":
                fname = os.path.basename(path_str)
                stem, ext = os.path.splitext(fname)
                if ext.lower() == ".exe" and stem.lower() not in IGNORED_FILES:
                    norm = normalize_path(path_str)
                    exes.append(
                        {
                            "path": norm,
                            "filename": fname,
                            "stem": stem,
                            "stem_lower": stem.lower(),
                            "rel_path": normalize_path(os.path.relpath(norm, self.sync_folder)),
                            "depth": int(item.get("depth", 0)),
                        }
                    )
            elif itype == "directory":
                dname = os.path.basename(path_str)
                if dname in jre:
                    jre[dname] = path_str

        return exes, jre

    def _match_xml(
        self, exes: List[Dict[str, Any]], folder_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        candidates = []
        for e in exes:
            stem = e["stem_lower"]
            name = self.repository.get_xml_game_name(stem)
            if not name:
                continue
            if stem in GENERIC_EXECUTABLE_STEMS and folder_name:
                if simple_match_score(folder_name, name) < 50:
                    continue
            candidates.append((e, name))

        if not candidates:
            return None

        # Best candidate by longest relative path match
        candidates.sort(key=lambda c: len(c[0]["rel_path"]), reverse=True)
        best_exe, xml_game_name = candidates[0]
        meta = self.repository.get_by_path(best_exe["rel_path"]) or self.repository.get_by_exe(best_exe["filename"])

        return {
            "exe_path": best_exe["path"],
            "game_name": meta["game_name"] if meta else xml_game_name,
            "steam_id": meta.get("steam_id") if meta else None,
            "lutris_id": meta.get("lutris_id") if meta else None,
            "gog_id": meta.get("gog_id") if meta else None,
            "files": meta.get("files", {}) if meta else {},
        }

    def _match_yaml_direct(
        self, exes: List[Dict[str, Any]], folder_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        for exe in sorted(exes, key=lambda x: x["depth"]):
            meta = self.repository.get_by_path(exe["rel_path"]) or self.repository.get_by_exe(exe["filename"])
            if meta:
                stem = exe["stem_lower"]
                if stem in GENERIC_EXECUTABLE_STEMS and folder_name:
                    if simple_match_score(folder_name, meta.get("game_name", "")) < 50:
                        continue
                return self._format_match(exe["path"], meta)
        return None

    def _match_java(self, jre_paths: Dict[str, Optional[str]]) -> Optional[Dict[str, Any]]:
        search_order = ["jre_x64", "jre"] if is_64bit_system() else ["jre", "jre_x64"]
        for jre_key in search_order:
            if not (base := jre_paths.get(jre_key)):
                continue
            for jexe in ("javaw.exe", "java.exe"):
                jpath = os.path.join(base, "bin", jexe)
                if os.path.exists(jpath):
                    rel = normalize_path(os.path.relpath(jpath, self.sync_folder))
                    if meta := (self.repository.get_by_path(rel) or self.repository.get_by_exe(jexe)):
                        return self._format_match(jpath, meta)
        return None

    def _match_fuzzy(self, folder_name: str, exes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not exes:
            return None

        # Fast direct lookup by executable name (excluding generic stems)
        for exe in exes:
            stem = exe["stem_lower"]
            if stem in GENERIC_EXECUTABLE_STEMS:
                continue
            if meta := (
                self.repository.get_by_path(exe["rel_path"])
                or self.repository.get_by_exe(exe["filename"])
                or self.repository.get_by_name(exe["stem_lower"])
            ):
                return self._format_match(exe["path"], meta)

        best_match, best_score = None, 0
        search_terms = {folder_name.lower()}
        for exe in exes:
            stem = exe["stem_lower"]
            if stem in GENERIC_EXECUTABLE_STEMS:
                continue
            search_terms.add(stem)
            search_terms.update(stem.split())
            cleaned = clean_executable_name(exe["path"]).lower()
            if cleaned and cleaned not in GENERIC_EXECUTABLE_STEMS:
                search_terms.add(cleaned)

        for term in search_terms:
            for match in self.repository.get_fuzzy_matches(term):
                score = simple_match_score(term, match["game_name"])
                if score > best_score:
                    best_score, best_match = score, match
                    if best_score == 100:
                        return self._format_match(exes[0]["path"], best_match)

        if best_match and best_score >= 50:
            return self._format_match(exes[0]["path"], best_match)

        best_exe = max(exes, key=lambda x: len(x["stem"]))
        return {
            "exe_path": best_exe["path"],
            "game_name": folder_name,
            "steam_id": "",
            "lutris_id": "",
            "gog_id": "",
            "files": {},
        }

    @staticmethod
    def _format_match(exe_path: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "exe_path": exe_path,
            "game_name": meta.get("game_name", os.path.basename(exe_path)),
            "steam_id": meta.get("steam_id", ""),
            "lutris_id": meta.get("lutris_id", ""),
            "gog_id": meta.get("gog_id", ""),
            "files": meta.get("files", {}),
        }
