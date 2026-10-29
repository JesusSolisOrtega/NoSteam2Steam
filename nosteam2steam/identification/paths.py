"""Architecture matching, launch conditions, and filesystem path resolution."""

import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional


def is_64bit_system() -> bool:
    """Returns True if the Python host process operates in 64-bit address space."""
    return sys.maxsize > 2**32


def supports_vulkan() -> bool:
    """Verifies Vulkan graphics API support on the local system."""
    try:
        return (
            subprocess.run(["vulkaninfo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).returncode == 0
        )
    except FileNotFoundError:
        return False


def is_steamos() -> bool:
    """Detects whether host environment is SteamOS or Steam Deck."""
    indicators = ("/usr/share/steamos", "/etc/steamos-release", str(Path.home() / "deck"), "/home/deck")
    try:
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release", "r", encoding="utf-8") as f:
                if "steamos" in f.read().lower():
                    return True
        return any(os.path.exists(i) for i in indicators)
    except Exception:
        return False


def normalize_path(path: str) -> str:
    """Normalizes separators to forward slashes and converts to lowercase."""
    return os.path.normpath(path).replace("\\", "/").lower()


def path_exists_case_insensitive(path: str, dir_cache: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Finds exact casing of path on case-sensitive filesystems using directory cache."""
    p = Path(path)
    if p.exists():
        return str(p)

    cache = dir_cache if dir_cache is not None else {}
    current = Path(p.root) if p.is_absolute() else Path(".")
    for part in p.parts[p.is_absolute() :]:
        key = str(current)
        if key not in cache:
            try:
                cache[key] = list(current.iterdir())
            except (OSError, PermissionError):
                return None
        matches = [c for c in cache[key] if c.name.lower() == part.lower()]
        if not matches:
            return None
        current = matches[0]

    return str(current)


def generate_alternative_paths(relative_path: str) -> List[str]:
    """Generates architecture-specific filename permutations (e.g. x64, win32)."""
    arch_pattern = re.compile(r"(x64|x86|x64vk|x86vk|win64|win32)", re.IGNORECASE)
    stem, ext = os.path.splitext(relative_path)
    matches = arch_pattern.findall(stem)
    if not matches:
        return [relative_path]

    variants = ("x64", "x86", "win64", "win32", "x64vk", "x86vk")
    alt = {relative_path}
    for m in matches:
        for v in variants:
            alt.add(stem.replace(m, v) + ext)
    return list(alt)


def select_best_path(relative_path: str, base_path: str) -> Optional[str]:
    """Selects the best available executable candidate matching host architecture and Vulkan."""
    dir_cache: Dict[str, List[str]] = {}
    is_64bit = is_64bit_system()
    supports_vk = supports_vulkan() or is_steamos()

    valid = []
    for candidate in generate_alternative_paths(relative_path):
        resolved = path_exists_case_insensitive(os.path.join(base_path, candidate), dir_cache)
        if resolved and os.path.isfile(resolved):
            valid.append(resolved)

    if not valid:
        return None

    def score(p: str) -> int:
        pl = p.lower()
        matched = ("x64" in pl or "win64" in pl) if is_64bit else ("x86" in pl or "win32" in pl)
        vk = "vk" in pl and supports_vk
        return 3 if (vk and matched) else 2 if matched else 1 if vk else 0

    return max(valid, key=score)


def sort_launch_paths(launch_paths: Dict[str, Any]) -> List[str]:
    """Ranks manifest launch paths according to current OS and architecture conditions."""
    current_os = platform.system().lower()
    is_64bit = is_64bit_system()
    prioritized = []

    for path, conditions in launch_paths.items():
        if current_os in ("windows", "linux") and path.endswith(".app"):
            continue

        priority = 2
        for cond in conditions:
            if isinstance(cond, dict) and "when" in cond:
                for when in cond["when"]:
                    if not isinstance(when, dict):
                        continue
                    when_os = when.get("os", "").lower()
                    when_bit = str(when.get("bit", ""))
                    if when_os == current_os and when_bit == ("64" if is_64bit else "32"):
                        priority = 0
                        break
                    elif when_os == current_os:
                        priority = min(priority, 1)

        prioritized.append((path, priority))

    prioritized.sort(key=lambda x: x[1])
    return [p for p, _ in prioritized]
