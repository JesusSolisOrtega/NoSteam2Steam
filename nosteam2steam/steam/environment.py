"""Steam environment detection: active user profiles, paths, and Proton runtimes."""

import logging
import os
import re
from pathlib import Path
from typing import Optional
import vdf

from nosteam2steam.steam.ids import steamid64_to_accountid

logger = logging.getLogger(__name__)


def _detect_steam_paths() -> Path:
    custom = os.getenv("STEAM_DIR") or os.getenv("STEAM_HOME") or os.getenv("STEAM_ROOT")
    if custom and Path(custom).expanduser().exists():
        return Path(custom).expanduser()
    candidates = [
        Path.home() / ".local/share/Steam",
        Path.home() / ".steam/steam",
        Path.home() / ".steam/root",
        Path.home() / ".steam/debian-installation",
        Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        Path.home() / "snap/steam/common/.local/share/Steam",
    ]
    for c in candidates:
        if (c / "steamapps").exists() or (c / "userdata").exists():
            return c
    return Path.home() / ".local/share/Steam"


_DETECTED_STEAM = _detect_steam_paths()
STEAM_USERDATA_DIR = (
    str(_DETECTED_STEAM / "userdata")
    if (_DETECTED_STEAM / "userdata").exists()
    else os.path.expanduser("~/.local/share/Steam/userdata")
)
SHORTCUTS_FILE = "shortcuts.vdf"
CONFIG_VDF_PATH = str(_DETECTED_STEAM / "config" / "config.vdf")
LOGINUSERS_PATH = str(_DETECTED_STEAM / "config" / "loginusers.vdf")
LOGINUSERS_PATHS = [
    str(_DETECTED_STEAM / "config" / "loginusers.vdf"),
    os.path.expanduser("~/.local/share/Steam/config/loginusers.vdf"),
    os.path.expanduser("~/.steam/steam/config/loginusers.vdf"),
    os.path.expanduser("~/.steam/root/config/loginusers.vdf"),
    os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam/config/loginusers.vdf"),
    os.path.expanduser("~/snap/steam/common/.local/share/Steam/config/loginusers.vdf"),
]

PROTON_DIRS = [
    str(_DETECTED_STEAM / "steamapps" / "common"),
    os.path.expanduser("~/.steam/root/steamapps/common"),
    os.path.expanduser("~/.local/share/Steam/steamapps/common"),
    os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common"),
    os.path.expanduser("~/snap/steam/common/.local/share/Steam/steamapps/common"),
]

PROTON_GE_DIRS = [
    str(_DETECTED_STEAM / "compatibilitytools.d"),
    os.path.expanduser("~/.steam/root/compatibilitytools.d"),
    os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
    os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam/compatibilitytools.d"),
    os.path.expanduser("~/snap/steam/common/.local/share/Steam/compatibilitytools.d"),
    "/usr/share/steam/compatibilitytools.d",
    "/usr/local/share/steam/compatibilitytools.d",
    "/usr/share/compatibilitytools.d",
]


def _get_config():
    try:
        import nosteam2steam.config as cfg

        return cfg
    except ImportError:
        return None


def get_steam_username(user_id: str) -> str:
    """Reads username alias from localconfig.vdf for a given user AccountID."""
    localconfig_path = os.path.join(STEAM_USERDATA_DIR, user_id, "config", "localconfig.vdf")
    if not os.path.exists(localconfig_path):
        logger.warning(f"File {localconfig_path} does not exist.")
        return user_id

    try:
        with open(localconfig_path, "r", encoding="utf-8") as f:
            localconfig = vdf.load(f)

        friends_section = localconfig.get("UserLocalConfigStore", {}).get("friends", {})
        user_info = friends_section.get(user_id, {})
        return str(user_info.get("name", user_id))
    except Exception as e:
        logger.error(f"Error reading localconfig.vdf: {e}")
        return user_id


def get_current_user() -> Optional[str]:
    """
    Detects the current active Steam AccountID.
    Prioritizes loginusers.vdf with MostRecent=1, falling back to modification timestamps
    and userdata directory inspection.
    """
    paths = getattr(_get_config(), "LOGINUSERS_PATHS", LOGINUSERS_PATHS)
    for loginusers_file in paths:
        if not os.path.exists(loginusers_file):
            continue
        try:
            with open(loginusers_file, "r", encoding="utf-8") as f:
                loginusers = vdf.load(f)
            users = loginusers.get("users", {})
            if not users:
                continue

            for user_id, user_data in users.items():
                most_recent = user_data.get("MostRecent") if "MostRecent" in user_data else user_data.get("mostrecent")
                if str(most_recent) == "1":
                    return str(steamid64_to_accountid(user_id))

            sorted_users = sorted(
                users.items(),
                key=lambda x: int(x[1].get("Timestamp", 0) or x[1].get("timestamp", 0)),
                reverse=True,
            )
            return str(steamid64_to_accountid(sorted_users[0][0]))
        except Exception as e:
            logger.error(f"Error reading {loginusers_file}: {e}")

    if os.path.exists(STEAM_USERDATA_DIR):
        try:
            user_dirs = [
                d
                for d in os.listdir(STEAM_USERDATA_DIR)
                if d.isdigit() and d != "0" and os.path.isdir(os.path.join(STEAM_USERDATA_DIR, d))
            ]
            if len(user_dirs) == 1:
                return user_dirs[0]
            elif len(user_dirs) > 1:
                user_dirs.sort(
                    key=lambda d: os.path.getmtime(os.path.join(STEAM_USERDATA_DIR, d)),
                    reverse=True,
                )
                return user_dirs[0]
        except Exception as e:
            logger.error(f"Error inspecting {STEAM_USERDATA_DIR}: {e}")

    return None


def get_user_config_dir(user_id: Optional[str] = None) -> Optional[str]:
    """Returns the config directory path for the specified or current Steam user."""
    uid = user_id or get_current_user()
    if not uid:
        return None
    return os.path.join(STEAM_USERDATA_DIR, uid, "config")


def get_shortcuts_path(user_id: Optional[str] = None) -> Optional[str]:
    """Returns absolute path to shortcuts.vdf for user."""
    config_dir = get_user_config_dir(user_id)
    if not config_dir:
        return None
    return os.path.join(config_dir, SHORTCUTS_FILE)


def get_localconfig_path(user_id: Optional[str] = None) -> Optional[str]:
    """Returns absolute path to localconfig.vdf for user."""
    config_dir = get_user_config_dir(user_id)
    if not config_dir:
        return None
    return os.path.join(config_dir, "localconfig.vdf")


def _unique_dirs(dir_list):
    seen = set()
    result = []
    for d in dir_list:
        if os.path.exists(d):
            real = os.path.realpath(d)
            if real not in seen:
                seen.add(real)
                result.append(d)
    return result


def get_latest_proton_ge(get_path: bool = False) -> Optional[str]:
    """Detects latest GE-Proton installation using numerical major/minor version sort."""
    candidates = []
    ge_dirs = getattr(_get_config(), "PROTON_GE_DIRS", PROTON_GE_DIRS)

    for proton_dir in _unique_dirs(ge_dirs):
        try:
            entries = os.listdir(proton_dir)
        except OSError as e:
            logger.debug(f"Could not list directory {proton_dir}: {e}")
            continue
        for dir_name in entries:
            if dir_name.startswith("GE-Proton"):
                match = re.search(r"GE-Proton(\d+)[-_](\d+)", dir_name)
                if match:
                    major, minor = int(match.group(1)), int(match.group(2))
                    path = os.path.join(proton_dir, dir_name) if get_path else dir_name
                    candidates.append(((major, minor), path))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    return None


def get_latest_proton(get_path: bool = False) -> Optional[str]:
    """Detects latest official Valve Proton runtime, prioritizing Proton Experimental over numbered releases."""
    candidates = []
    experimental_tool = None
    cfg = _get_config()
    default_dirs = getattr(cfg, "PROTON_DIRS", PROTON_DIRS)
    all_dirs = list(default_dirs)
    if default_dirs is PROTON_DIRS and cfg and hasattr(cfg, "get_steam_library_folders"):
        try:
            for lib in cfg.get_steam_library_folders():
                lib_common = str(lib / "steamapps" / "common")
                if lib_common not in all_dirs and os.path.exists(lib_common):
                    all_dirs.append(lib_common)
        except Exception:
            pass

    for proton_dir in _unique_dirs(all_dirs):
        try:
            entries = os.listdir(proton_dir)
        except OSError as e:
            logger.debug(f"Could not list directory {proton_dir}: {e}")
            continue
        for dir_name in entries:
            if dir_name in ("Proton Experimental", "Proton - Experimental"):
                if not experimental_tool:
                    experimental_tool = os.path.join(proton_dir, dir_name) if get_path else dir_name
            elif dir_name.startswith("Proton"):
                match = re.search(r"Proton(?:\s*-\s*|\s+)(\d+(?:\.\d+)?)", dir_name)
                if match:
                    ver_tuple = tuple(map(int, match.group(1).split(".")))
                    path = os.path.join(proton_dir, dir_name) if get_path else dir_name
                    candidates.append((ver_tuple, path))

    if experimental_tool:
        return experimental_tool
    elif candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


def get_proton_version(get_path: bool = False) -> Optional[str]:
    """Finds best available Proton version, prioritizing GE-Proton over official releases."""
    version = get_latest_proton_ge(get_path)
    if not version:
        version = get_latest_proton(get_path)
    return version
