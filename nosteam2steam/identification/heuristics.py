"""Heuristic scoring, string similarity metrics, and executable candidate selection."""

import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Set

from nosteam2steam.config import IGNORED_FILES

PREFIXES = ["Launcher_", "Game_", "Steam_", "Uplay_", "Epic_", "GOG_", "Retail_", "Demo_"]
SUFFIXES = [
    "_Launcher",
    "_Game",
    "_Win",
    "_64",
    "_x64",
    "_32",
    "_x86",
    "_Main",
    "_Shipping",
    "_Final",
    "_Beta",
    "_Test",
    "_Trial",
    "_DX11",
    "_DX12",
    "_VR",
    "-Win64-Shipping",
    "Win64-Shipping",
]
GENERIC_NAMES = {
    "game",
    "launcher",
    "start",
    "play",
    "run",
    "main",
    "shipping",
    "app",
    "x64",
    "x86",
    "win64",
    "win32",
    "64",
    "32",
}


def clean_executable_name(exe_path: str) -> str:
    """Normalizes executable names by stripping launcher/architecture affixes and casing."""
    path_obj = Path(exe_path)
    stem = path_obj.stem
    changed = True
    while changed:
        changed = False
        for prefix in PREFIXES:
            if stem.lower().startswith(prefix.lower()):
                stem = stem[len(prefix) :]
                changed = True
        for suffix in SUFFIXES:
            if stem.lower().endswith(suffix.lower()):
                stem = stem[: -len(suffix)]
                changed = True

    stem = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)
    stem = stem.replace("_", " ").replace("-", " ").strip()

    if not stem or stem.lower() in GENERIC_NAMES:
        parent = path_obj.parent
        if parent.name.lower() in {"bin", "x64", "x86", "win64", "win32", "shipping", "retail"}:
            parent = parent.parent
        stem = parent.name
    if stem.islower():
        stem = stem.title()
    return stem


def calculate_name_similarity(name1: str, name2: str) -> int:
    """Calculates numerical similarity score based on substring containment and common prefix."""
    n1, n2 = name1.lower(), name2.lower()
    if n1 in n2 or n2 in n1:
        return max(len(n1), len(n2))

    prefix = 0
    for c1, c2 in zip(n1, n2):
        if c1 == c2:
            prefix += 1
        else:
            break
    return prefix


def simple_match_score(a: str, b: str) -> int:
    """Computes alphanumeric similarity score between two strings for fuzzy candidate ranking."""
    a_low, b_low = a.lower(), b.lower()
    if a_low == b_low:
        return 100
    if a_low in b_low or b_low in a_low:
        return 90
    sa, sb = a_low.split(), b_low.split()
    max_len = max(len(sa), len(sb))
    return int(80 * len(set(sa) & set(sb)) / max_len) if max_len else 0


def find_best_exe_in_folder(
    folder_path: str,
    reference_name: str,
    search_subdirs: bool = False,
    items_to_search: Optional[List[Dict[str, Any]]] = None,
    get_directory_contents: Optional[Callable[[str], Dict[str, List[str]]]] = None,
    ignored_files: Optional[Set[str]] = None,
) -> Optional[str]:
    """Finds executable (.exe) in folder best matching the reference title by lexical similarity."""
    ignored = ignored_files or IGNORED_FILES
    best_exe: Optional[str] = None
    best_score = -1

    candidates: List[str] = []
    if items_to_search:
        candidates = [
            str(item["path"])
            for item in items_to_search
            if item.get("type") == "file" and str(item.get("path", "")).lower().endswith(".exe")
        ]
    elif os.path.isdir(folder_path):
        try:
            candidates = [
                os.path.join(folder_path, f)
                for f in os.listdir(folder_path)
                if f.lower().endswith(".exe") and os.path.isfile(os.path.join(folder_path, f))
            ]
        except OSError:
            pass

    for exe_path in candidates:
        stem = os.path.splitext(os.path.basename(exe_path))[0]
        if stem.lower() in ignored:
            continue
        score = calculate_name_similarity(stem, reference_name)
        if score > best_score:
            best_score, best_exe = score, exe_path

    return best_exe
