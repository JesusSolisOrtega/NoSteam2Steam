"""Sync directory discovery and configuration file persistence."""

import configparser
import json
import logging
import os
from pathlib import Path
from typing import List

from nosteam2steam.config import (
    DEFAULT_SYNC_FOLDER,
    GOG_PATHS,
    HEROIC_PATHS,
    LUTRIS_CONFIG_PATHS,
    SYNC_FOLDERS_FILE,
)

logger = logging.getLogger(__name__)


def get_default_sync_folders() -> List[str]:
    """
    Discovers default game installation folders across multiple Linux distributions,
    package managers (Flatpak, Snap, Native), third-party launchers, and mount points.
    """
    folders = {DEFAULT_SYNC_FOLDER}

    # 1. Heroic Games Launcher (Native & Flatpak)
    for path in HEROIC_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if "defaultInstallPath" in cfg and os.path.isdir(cfg["defaultInstallPath"]):
                        folders.add(cfg["defaultInstallPath"])
            except Exception:
                continue

    heroic_config_dirs = [
        Path.home() / ".config/heroic",
        Path.home() / ".var/app/com.heroicgameslauncher.hgl/config/heroic",
    ]
    for h_dir in heroic_config_dirs:
        for store_file in (
            h_dir / "gog_store/installed.json",
            h_dir / "legendaryConfig/legendary/installed.json",
            h_dir / "nile_store/installed.json",
        ):
            if store_file.exists():
                try:
                    with open(store_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    installed = data.get("installed", [])
                    items = (
                        installed
                        if isinstance(installed, list)
                        else installed.values()
                        if isinstance(installed, dict)
                        else []
                    )
                    for item in items:
                        if isinstance(item, dict) and "install_path" in item:
                            ip = Path(item["install_path"])
                            if ip.exists():
                                folders.add(str(ip.parent))
                except Exception:
                    pass

    heroic_default = os.path.join(Path.home(), "Games", "Heroic")
    if any(os.path.exists(p) for p in HEROIC_PATHS) or os.path.exists(heroic_default):
        folders.add(heroic_default)

    # 2. Lutris (Native & Flatpak)
    for lutris_cfg in LUTRIS_CONFIG_PATHS:
        if os.path.exists(lutris_cfg):
            try:
                parser = configparser.ConfigParser()
                parser.read(lutris_cfg, encoding="utf-8")
                if parser.has_section("lutris") and "game_path" in parser["lutris"]:
                    lp = os.path.expanduser(parser["lutris"]["game_path"])
                    if os.path.isdir(lp):
                        folders.add(lp)
            except Exception:
                pass

    lutris_default = os.path.join(Path.home(), "Games", "lutris")
    if os.path.isdir(lutris_default):
        folders.add(lutris_default)

    # 3. Bottles (Native & Flatpak)
    bottles_paths = [
        Path.home() / ".var/app/com.usebottles.bottles/data/bottles/bottles",
        Path.home() / ".local/share/bottles/bottles",
    ]
    for bp in bottles_paths:
        if bp.exists():
            folders.add(str(bp))

    # 4. Steam configured library folders
    try:
        from nosteam2steam.config import get_steam_library_folders

        for lib in get_steam_library_folders():
            lib_games = lib / "Games"
            if lib_games.is_dir():
                folders.add(str(lib_games))
    except Exception:
        pass

    # 5. Steam Deck MicroSD direct check
    if os.path.exists("/run/media/mmcblk0p1"):
        mmc_games = "/run/media/mmcblk0p1/Games"
        folders.add(mmc_games if os.path.isdir(mmc_games) else "/run/media/mmcblk0p1")

    # 6. Multi-Distro removable media and mount points (Steam Deck, Arch, Fedora, Debian, Ubuntu)
    mount_bases = ["/run/media", "/media", "/mnt"]
    for base in mount_bases:
        if not os.path.exists(base):
            continue

        try:
            for top_entry in os.listdir(base):
                top_path = os.path.join(base, top_entry)
                if not os.path.isdir(top_path):
                    continue

                # Check if base contains user subfolder (e.g. /run/media/deck, /media/username)
                try:
                    sub_entries = [
                        os.path.join(top_path, s)
                        for s in os.listdir(top_path)
                        if os.path.isdir(os.path.join(top_path, s))
                    ]
                except (OSError, PermissionError):
                    sub_entries = []

                if sub_entries:
                    for drive in sub_entries:
                        games_candidate = os.path.join(drive, "Games")
                        if os.path.isdir(games_candidate):
                            folders.add(games_candidate)
                        else:
                            folders.add(drive)
                else:
                    # Direct mount (e.g. /mnt/Games or /mnt/Storage)
                    games_candidate = os.path.join(top_path, "Games")
                    if os.path.isdir(games_candidate):
                        folders.add(games_candidate)
                    elif top_entry.lower() in ("games", "juegos", "storage", "steamlibrary"):
                        folders.add(top_path)
        except (OSError, PermissionError):
            pass

    # GOG Galaxy on Windows
    if os.name == "nt":
        for path in GOG_PATHS:
            if os.path.exists(path):
                if path.endswith(".json"):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                            if "libraryPath" in cfg:
                                folders.add(cfg["libraryPath"])
                    except Exception:
                        continue
                else:
                    folders.add(os.path.join(Path.home(), "GOG Games"))

    return list(folders)


def get_sync_folders() -> List[str]:
    """Reads configured sync folders from file or initializes it with default discovered paths."""
    lines: List[str] = []
    if os.path.exists(SYNC_FOLDERS_FILE):
        try:
            with open(SYNC_FOLDERS_FILE, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
        except OSError as e:
            logger.error(f"Error reading {SYNC_FOLDERS_FILE}: {e}")
            return [DEFAULT_SYNC_FOLDER]

    if not lines:
        defaults = get_default_sync_folders()
        try:
            with open(SYNC_FOLDERS_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(defaults))
            return [d for d in defaults if os.path.exists(d)]
        except OSError as e:
            logger.error(f"Error initializing {SYNC_FOLDERS_FILE}: {e}")
            return [DEFAULT_SYNC_FOLDER]

    valid = [f for f in lines if os.path.exists(f)]
    return valid or [DEFAULT_SYNC_FOLDER]

