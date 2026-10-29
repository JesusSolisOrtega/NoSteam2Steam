import logging
import os
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def get_noSteam2Steam_dir() -> Path:
    """
    Returns the application data directory following the XDG Base Directory specification.
    If a legacy directory (~/noSteam2Steam_Data) exists, it is migrated to preserve existing configuration.
    """
    legacy_dir = Path.home() / "noSteam2Steam_Data"
    xdg_data_home = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share"))
    xdg_dir = xdg_data_home / "noSteam2Steam"

    if legacy_dir.exists() and not xdg_dir.exists():
        try:
            xdg_dir.parent.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copytree(str(legacy_dir), str(xdg_dir))
            return xdg_dir
        except Exception:
            return legacy_dir

    if xdg_dir.exists():
        return xdg_dir

    if legacy_dir.exists():
        return legacy_dir

    xdg_dir.mkdir(parents=True, exist_ok=True)
    return xdg_dir


def get_resource_path(relative_path: str) -> str:
    """Resolves path to static resources, supporting standalone PyInstaller bundles and source trees."""
    base_path = getattr(sys, "_MEIPASS", None)
    if base_path:
        target = os.path.join(base_path, relative_path)
        if os.path.exists(target):
            return target
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(pkg_dir)
    in_pkg = os.path.join(pkg_dir, relative_path)
    if os.path.exists(in_pkg):
        return in_pkg
    return os.path.join(root_dir, relative_path)


# main modules files paths
SCRIPT_DIR = get_noSteam2Steam_dir()

log_file = SCRIPT_DIR / "no_steam_to_steam.log"
file_handler = RotatingFileHandler(str(log_file), maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])

logger = logging.getLogger(__name__)

# config paths
DEFAULT_SYNC_FOLDER = str(Path.home() / "Games")
SYNC_FOLDERS_FILE = os.path.join(SCRIPT_DIR, "sync_folders.txt")
INVENTORY_FILE = str(os.path.join(SCRIPT_DIR, "games_backups_inventory.json"))
STEAM_ID_MAPPING_FILE = str(os.path.join(SCRIPT_DIR, "steam_id_mapping.json"))
DEFAULT_GAMES_INFO_PATH = os.path.join(SCRIPT_DIR, "games.json")
USER_MAPPING_PATH = os.path.join(SCRIPT_DIR, "user_mapping.json")
XML_FILE = os.path.join(SCRIPT_DIR, "GBM_Official.xml")
YAML_FILE = os.path.join(SCRIPT_DIR, "manifest.yaml")
INDEX_DIR = os.path.join(SCRIPT_DIR, "indexes")
LANGUAGE_FILE = os.path.join(SCRIPT_DIR, "language.txt")
UNMATCHED_CANDIDATES_FILE = os.path.join(SCRIPT_DIR, "unmatched_candidates.json")
XML_URL = "https://github.com/MikeMaximus/gbm-web/blob/gh-pages/GBM_Official.xml?raw=true"
YAML_URL = "https://raw.githubusercontent.com/mtkennerly/ludusavi-manifest/refs/heads/master/data/manifest.yaml"

# Saves related paths
def get_steam_root() -> Path:
    """
    Finds active Steam root installation directory on Linux/SteamOS.
    Supports native distributions, Flatpak (Flathub), Snap, and environment overrides.
    """
    custom = os.getenv("STEAM_DIR") or os.getenv("STEAM_HOME") or os.getenv("STEAM_ROOT")
    if custom:
        p = Path(custom).expanduser()
        if p.exists():
            return p

    candidates = [
        # Native package installations (Arch, Fedora, openSUSE, Debian, Ubuntu, SteamOS)
        Path.home() / ".local/share/Steam",
        Path.home() / ".steam/steam",
        Path.home() / ".steam/root",
        Path.home() / ".steam/debian-installation",
        # Flatpak Steam (Flathub com.valvesoftware.Steam)
        Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        Path.home() / ".var/app/com.valvesoftware.Steam/.steam/steam",
        # Snap Steam (Ubuntu Snap Store)
        Path.home() / "snap/steam/common/.local/share/Steam",
        Path.home() / "snap/steam/common/.steam/steam",
    ]
    for candidate in candidates:
        if (candidate / "steamapps").exists() or (candidate / "userdata").exists():
            return candidate
    return Path.home() / ".local/share/Steam"


def get_steam_library_folders(steam_root: Path | None = None) -> list[Path]:
    """
    Parses libraryfolders.vdf to discover all registered Steam library directories
    across multiple physical drives, partitions, or MicroSD cards.
    """
    import vdf

    root = steam_root or get_steam_root()
    libraries: list[Path] = [root]
    vdf_file = root / "steamapps" / "libraryfolders.vdf"
    if not vdf_file.exists():
        return libraries

    try:
        with open(vdf_file, "r", encoding="utf-8") as f:
            data = vdf.load(f)
        folders = data.get("libraryfolders", {})
        for _, lib_data in folders.items():
            if isinstance(lib_data, dict) and "path" in lib_data:
                p = Path(lib_data["path"])
                if p.exists() and p not in libraries:
                    libraries.append(p)
    except Exception as e:
        logger.warning(f"Error reading libraryfolders.vdf: {e}")

    return libraries


def get_all_compatdata_dirs(steam_root: Path | None = None) -> list[Path]:
    """
    Discovers all directories containing Proton compatdata prefixes across all
    Steam library locations, Flatpak containers, and secondary storage drives.
    """
    root = steam_root or get_steam_root()
    compat_dirs: list[Path] = []

    primary = root / "steamapps" / "compatdata"
    if primary.exists():
        compat_dirs.append(primary)

    # Check alternate installation roots (e.g. Flatpak or native secondary)
    alternate_roots = [
        Path.home() / ".local/share/Steam",
        Path.home() / ".steam/steam",
        Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        Path.home() / "snap/steam/common/.local/share/Steam",
    ]
    for alt in alternate_roots:
        alt_compat = alt / "steamapps" / "compatdata"
        if alt_compat.exists() and alt_compat not in compat_dirs:
            compat_dirs.append(alt_compat)

    # Inspect all configured library folders
    for lib in get_steam_library_folders(root):
        lib_compat = lib / "steamapps" / "compatdata"
        if lib_compat.exists() and lib_compat not in compat_dirs:
            compat_dirs.append(lib_compat)

    return compat_dirs


STEAM_ROOT = get_steam_root()
STEAMDECK_PATH = STEAM_ROOT / "steamapps/compatdata"
STEAM_USERDATA_DIR = (
    str(STEAM_ROOT / "userdata")
    if (STEAM_ROOT / "userdata").exists()
    else os.path.expanduser("~/.local/share/Steam/userdata")
)
DEFAULT_BACKUPS_PATH = Path.home() / "Backups"
ALTERNATIVE_BACKUPS_PATH_FILE = SCRIPT_DIR / "alternative_backups_path.txt"
ID_MAP_PATH = SCRIPT_DIR / "steam_id_mapping.json"
SYNC_RECORD_FILE = str(SCRIPT_DIR / "sync_record.json")
ROOT_PATH = STEAM_ROOT


def get_backups_directory() -> Path:
    try:
        script_dir = SCRIPT_DIR.resolve()
        config_file = ALTERNATIVE_BACKUPS_PATH_FILE
        target_directory = DEFAULT_BACKUPS_PATH

        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                custom_path = f.read().strip()
                if custom_path:
                    custom_path_obj = Path(custom_path)
                    if custom_path_obj.is_absolute() and custom_path_obj.is_dir():
                        target_directory = custom_path_obj
                    else:
                        resolved_path = (script_dir / custom_path_obj).resolve()
                        if resolved_path.is_dir():
                            target_directory = resolved_path
                        else:
                            logger.warning(f"Configured path is not valid: {custom_path}")

        target_directory.mkdir(parents=True, exist_ok=True)
        return target_directory
    except Exception as e:
        logger.error(f"Error reading configuration: {e}")
        DEFAULT_BACKUPS_PATH.mkdir(parents=True, exist_ok=True)
        return DEFAULT_BACKUPS_PATH


# Identify_games.py
IGNORED_FILES = {
    "unitycrashhandler64",
    "unitycrashhandler32",
    "buildpotfile",
    "msgfmt",
    "._unitycrashhandler64",
    "jjs",
    "unpack200",
    "ssvagent",
    "java-rmi",
    "pack200",
    "jp2launcher",
    "unins000",
    "localization",
    "steam_workshop_upload",
    "savegametransfer",
    "msar-win64-shipping",
    "ue4prereqsetup_x64",
    "atlastool",
    "paktool",
    "scripttool",
    "cdbtool",
    "tmxtool",
    "dxwebsetup",
    "vcredist",
    "vcredist_x64",
    "vcredist_x86",
    "setup",
    "setup_x64",
    "setup_x86",
    "installscript",
    "installscript_x64",
    "installscript_x86",
    "quicksvf",
    "dotnetfx",
    "directxsetup",
    "eulas",
    "physx",
    "gameuxinstallhelper",
    "gfwlivesetup",
    "gfwlclient",
    "installutil",
    "patchinstaller",
    "registerdll",
    "uninstall",
    "bootstrapper",
    "launcher",
    "helper",
    "supporttool",
    "troubleshooter",
    "repairtool",
    "activation",
    "activationui",
    "configtool",
    "updater",
    "update",
    "patcher",
    "patch",
    "redistributable",
    "redistributables",
    "prerequisite",
    "prerequisites",
    "unins001",
    "unins002",
    "unins003",
    "unins004",
    "unins005",
    "unins006",
    "unins007",
    "unins008",
    "unins009",
    "unins010",
    "unins011",
    "unins012",
    "unins013",
    "unins014",
    "unins015",
    "unins016",
    "unins017",
    "unins018",
}

IGNORED_DIRS = {
    "heroic",
    "prefixes",
    "_commonredist",
    "_redist",
    "commonredist",
    "redist",
    "redistributables",
    "prerequisites",
    "support",
    "extras",
    "tools",
    "update",
    "patches",
    "patch",
    "installer",
    "installers",
    "setup",
    "noSteam2Steam",
}

ASSET_DIRS = {
    "content",
    "paks",
    "audio",
    "sound",
    "sounds",
    "music",
    "textures",
    "videos",
    "movies",
    "localization",
    "languages",
    "locale",
    "shaders",
    "node_modules",
    "dosdevices",
    "drive_c",
    "dlc",
}

GENERIC_EXECUTABLE_STEMS = {
    "game",
    "main",
    "start",
    "play",
    "app",
    "client",
    "launch",
    "launcher",
    "run",
    "loader",
    "player",
    "binary",
    "shipping",
    "wrapper",
    "default",
}

HEROIC_PATHS = [
    os.path.join(Path.home(), ".config", "heroic", "config.json"),  # Native Linux Heroic config
    os.path.join(
        Path.home(), ".var", "app", "com.heroicgameslauncher.hgl", "config", "heroic", "config.json"
    ),  # Flatpak Heroic config
    os.path.join(Path.home(), ".config", "heroic", "gamesConfig.json"),  # Native Linux gamesConfig
    os.path.join(
        Path.home(), ".var", "app", "com.heroicgameslauncher.hgl", "config", "heroic", "gamesConfig.json"
    ),  # Flatpak gamesConfig
    os.path.join(os.getenv("APPDATA", ""), "heroic", "gamesConfig.json"),  # Windows
    os.path.join(Path.home(), "Library", "Application Support", "heroic", "gamesConfig.json"),  # macOS
]

LUTRIS_CONFIG_PATHS = [
    os.path.join(Path.home(), ".config", "lutris", "lutris.conf"),  # Native Linux Lutris
    os.path.join(Path.home(), ".var", "app", "net.lutris.Lutris", "config", "lutris", "lutris.conf"),  # Flatpak Lutris
]

GOG_PATHS = [
    os.path.join(os.getenv("PROGRAMFILES", ""), "GOG Galaxy", "Games"),  # Windows
    os.path.join(os.getenv("LOCALAPPDATA", ""), "GOG.com", "Galaxy", "Configuration", "config.json"),  # Windows config
]

# utils.py
SERVICE_FILE = Path("~/.config/systemd/user/syncthingy.service").expanduser()

# SteamID generation and calculations
from nosteam2steam.steam.ids import (
    STEAMID64_BASE,
    accountid_to_steamid64,
    generate_app_id,
    generate_preliminary_id,
    generate_short_app_id,
    generate_shortcut_id,
    steamid64_to_accountid,
)

# Paths and configuration constants

# Steam environment and runtime detection
from nosteam2steam.steam.environment import (
    CONFIG_VDF_PATH,
    LOGINUSERS_PATH,
    LOGINUSERS_PATHS,
    PROTON_DIRS,
    PROTON_GE_DIRS,
    SHORTCUTS_FILE,
    get_current_user,
    get_latest_proton,
    get_latest_proton_ge,
    get_localconfig_path,
    get_proton_version,
    get_shortcuts_path,
    get_steam_username,
    get_user_config_dir,
)

__all__ = [
    "get_noSteam2Steam_dir",
    "get_resource_path",
    "get_backups_directory",
    "get_steam_root",
    "get_steam_library_folders",
    "get_all_compatdata_dirs",
    "SCRIPT_DIR",
    "DEFAULT_SYNC_FOLDER",
    "SYNC_FOLDERS_FILE",
    "INVENTORY_FILE",
    "UNMATCHED_CANDIDATES_FILE",
    "STEAM_ID_MAPPING_FILE",
    "XML_FILE",
    "YAML_FILE",
    "INDEX_DIR",
    "XML_URL",
    "YAML_URL",
    "STEAMDECK_PATH",
    "DEFAULT_BACKUPS_PATH",
    "ALTERNATIVE_BACKUPS_PATH_FILE",
    "ID_MAP_PATH",
    "SYNC_RECORD_FILE",
    "ROOT_PATH",
    "IGNORED_FILES",
    "IGNORED_DIRS",
    "ASSET_DIRS",
    "GENERIC_EXECUTABLE_STEMS",
    "HEROIC_PATHS",
    "LUTRIS_CONFIG_PATHS",
    "GOG_PATHS",
    "SERVICE_FILE",
    "STEAMID64_BASE",
    "generate_preliminary_id",
    "generate_app_id",
    "generate_short_app_id",
    "generate_shortcut_id",
    "steamid64_to_accountid",
    "accountid_to_steamid64",
    "DEFAULT_GAMES_INFO_PATH",
    "USER_MAPPING_PATH",
    "CONFIG_VDF_PATH",
    "LOGINUSERS_PATH",
    "LOGINUSERS_PATHS",
    "PROTON_DIRS",
    "PROTON_GE_DIRS",
    "SHORTCUTS_FILE",
    "STEAM_USERDATA_DIR",
    "get_current_user",
    "get_latest_proton",
    "get_latest_proton_ge",
    "get_localconfig_path",
    "get_proton_version",
    "get_shortcuts_path",
    "get_steam_username",
    "get_user_config_dir",
]
