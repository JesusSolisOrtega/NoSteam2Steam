import os
from pathlib import Path
import binascii
import re
import sys
import vdf
import logging


def get_noSteam2Steam_dir():
    program_data_folder_name = "noSteam2Steam_Data"
    home_dir = Path.home()
    data_dir = home_dir / program_data_folder_name
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

# Replace the original get_resource_path function with this one
# to ensure compatibility with PyInstaller.
'''
def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)
'''

def get_resource_path(relative_path):
    base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# main modules files paths
SCRIPT_DIR = get_noSteam2Steam_dir()
MANUAL_ADD_SCRIPT = get_resource_path(os.path.join("identify_game", "src", "main.sh"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(str(SCRIPT_DIR / "no_steam_to_steam.log")),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("no_steam_to_steam.log")

# config paths
DEFAULT_SYNC_FOLDER = os.path.expanduser("~/home/Games")
SYNC_FOLDERS_FILE = os.path.join(SCRIPT_DIR, "sync_folders.txt")
INVENTORY_FILE = str(os.path.join(SCRIPT_DIR, "games_backups_inventory.json"))
STEAM_ID_MAPPING_FILE = str(os.path.join(SCRIPT_DIR, "steam_id_mapping.json"))
XML_FILE = os.path.join(SCRIPT_DIR, "GBM_Official.xml")
YAML_FILE = os.path.join(SCRIPT_DIR, "manifest.yaml")
INDEX_DIR = os.path.join(SCRIPT_DIR, "indexes")
XML_URL = "https://github.com/MikeMaximus/gbm-web/blob/gh-pages/GBM_Official.xml?raw=true"
YAML_URL = "https://raw.githubusercontent.com/mtkennerly/ludusavi-manifest/refs/heads/master/data/manifest.yaml"

# Saves related paths
STEAMDECK_PATH = Path("/home/deck/.local/share/Steam/steamapps/compatdata")
DEFAULT_BACKUPS_PATH = Path("/home/deck/Backups")
ALTERNATIVE_BACKUPS_PATH_FILE = SCRIPT_DIR / "alternative_backups_path.txt"
ID_MAP_PATH = SCRIPT_DIR / "steam_id_mapping.json"
SYNC_RECORD_FILE = str(SCRIPT_DIR / "sync_record.json")
ROOT_PATH = Path("/home/deck/.local/share/Steam/steamapps")

def get_backups_directory():
    try:
        script_dir = SCRIPT_DIR.resolve()
        config_file = ALTERNATIVE_BACKUPS_PATH_FILE
        default_directory = DEFAULT_BACKUPS_PATH
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                custom_path = f.read().strip()
                if custom_path: 
                    custom_path = Path(custom_path)
                    if custom_path.is_absolute() and custom_path.is_dir():
                        return str(custom_path)
                    else:
                        resolved_path = (script_dir / custom_path).resolve()
                        if resolved_path.is_dir():
                            return str(resolved_path)
                        logger.warning(f"Configured path is not valid: {custom_path}")
        
        if not default_directory.exists():
            logger.info(f"Creating default backups directory at: {default_directory}")
            default_directory.mkdir(parents=True)

        return default_directory
    except Exception as e:
        logger.error(f"Error reading configuration: {e}")
        return DEFAULT_BACKUPS_PATH

# Identify_games.py
IGNORED_FILES = {
    "unitycrashhandler64", "unitycrashhandler32", "buildpotfile", "msgfmt", "._unitycrashhandler64",
    "jjs", "unpack200", "ssvagent", "java-rmi", "pack200", "jp2launcher", "unins000", "localization",
    "steam_workshop_upload", "savegametransfer", "msar-win64-shipping", "ue4prereqsetup_x64", "atlastool",
    "paktool", "scripttool", "cdbtool", "tmxtool", "dxwebsetup", "vcredist", "vcredist_x64", "vcredist_x86",
    "setup", "setup_x64", "setup_x86", "installscript", "installscript_x64", "installscript_x86", "quicksvf",
    "dotnetfx", "directxsetup", "eulas", "physx", "gameuxinstallhelper", "gfwlivesetup", "gfwlclient",
    "installutil", "patchinstaller", "registerdll", "uninstall", "bootstrapper", "launcher", "helper",
    "supporttool", "troubleshooter", "repairtool", "activation", "activationui", "configtool", "updater",
    "update", "patcher", "patch", "redistributable", "redistributables", "prerequisite", "prerequisites",
    "unins001", "unins002", "unins003", "unins004", "unins005", "unins006", "unins007", "unins008", "unins009",
    "unins010", "unins011", "unins012", "unins013", "unins014", "unins015", "unins016", "unins017", "unins018",
    }

IGNORED_DIRS = {
    "heroic", "prefixes", "_commonredist", "_redist", "commonredist", "redist", "redistributables", 
    "prerequisites", "support", "extras", "tools", "update", "patches", "patch", "installer", 
    "installers", "setup", "noSteam2Steam"
    }

HEROIC_PATHS = [
        os.path.join(Path("/home/deck/.var/app/com.heroicgameslauncher.hgl/config/heroic"),"config.json"),  # Steam Deck
        os.path.join(Path.home(), ".config", "heroic", "gamesConfig.json"),  # Linux config
        os.path.join(os.getenv("APPDATA", ""), "heroic", "gamesConfig.json"),  # Windows
        os.path.join(Path.home(), "Library", "Application Support", "heroic", "gamesConfig.json")  # macOS
    ]

GOG_PATHS = [
    os.path.join(os.getenv("PROGRAMFILES", ""), "GOG Galaxy", "Games"),  # Windows
    os.path.join(os.getenv("LOCALAPPDATA", ""), "GOG.com", "Galaxy", "Configuration", "config.json")  # Windows config
    ]

# utils.py
SERVICE_FILE = Path("~/.config/systemd/user/syncthingy.service").expanduser()

# SteamID generation
STEAMID64_BASE = 76561197960265728

def generate_preliminary_id(exe, app_name):

    key = (exe + app_name).encode("utf-8") 
    crc32_hash = binascii.crc32(key) 
    top = crc32_hash | 0x80000000 
    return (top << 32) | 0x02000000 

def generate_app_id(exe, app_name):

    return str(generate_preliminary_id(exe, app_name))

def generate_short_app_id(exe, app_name):

    return str(generate_preliminary_id(exe, app_name) >> 32)

def generate_shortcut_id(exe, app_name):

    return (generate_preliminary_id(exe, app_name) >> 32) - 0x100000000

def steamid64_to_accountid(steamid64):
    return int(steamid64) - STEAMID64_BASE

def accountid_to_steamid64(accountid):
    return int(accountid) + STEAMID64_BASE

# User info
def get_steam_username(user_id):

    localconfig_path = os.path.join(STEAM_USERDATA_DIR, user_id, "config", "localconfig.vdf")
    if not os.path.exists(localconfig_path):
        logging.warning(f"El archivo {localconfig_path} no existe.")
        return user_id 

    try:
        with open(localconfig_path, "r", encoding="utf-8") as f:
            localconfig = vdf.load(f)
        
        friends_section = localconfig.get("UserLocalConfigStore", {}).get("friends", {})
        
        user_info = friends_section.get(user_id, {})
        username = user_info.get("name", user_id) 
        
        return username
    except Exception as e:
        logging.error(f"Error reading localconfig.vdf: {e}")
        return user_id 

def get_current_user():
    
    if not os.path.exists(LOGINUSERS_PATH):
        return None

    try:
        with open(LOGINUSERS_PATH, "r") as f:
            loginusers = vdf.load(f)
        
        for user_id, user_data in loginusers.get("users", {}).items():
            if user_data.get("MostRecent", "0") == "1":
                return str(steamid64_to_accountid(user_id))
        return None
    except Exception as e:
        logging.error(f"Error reading loginusers.vdf: {e}")
        return None

# add2Steam.py
STEAM_USERDATA_DIR = os.path.expanduser("~/.local/share/Steam/userdata")
SHORTCUTS_FILE = "shortcuts.vdf"
DEFAULT_GAMES_INFO_PATH = os.path.join(SCRIPT_DIR, "games.json")
USER_MAPPING_PATH = os.path.join(SCRIPT_DIR, "user_mapping.json")
CONFIG_VDF_PATH = os.path.expanduser("~/.steam/steam/config/config.vdf")
LOGINUSERS_PATH = os.path.expanduser("~/.local/share/Steam/config/loginusers.vdf")

USER_CONFIG_DIR = os.path.join(STEAM_USERDATA_DIR, get_current_user(), "config")
shortcuts_path = os.path.join(USER_CONFIG_DIR, SHORTCUTS_FILE)
LOCALCONFIG_PATH = os.path.join(STEAM_USERDATA_DIR, get_current_user(), "config", "localconfig.vdf")

# Proton
PROTON_DIRS = [
    os.path.expanduser("~/.steam/root/steamapps/common"),
    os.path.expanduser("~/.local/share/Steam/steamapps/common")
]

PROTON_GE_DIRS = [
    os.path.expanduser("~/.steam/root/compatibilitytools.d"),
    os.path.expanduser("~/.local/share/Steam/compatibilitytools.d")
]

def get_latest_proton_ge(get_path=False):
    
    latest_version = None
    tool_version = None

    for proton_dir in PROTON_GE_DIRS:
        if os.path.exists(proton_dir):
            for dir_name in os.listdir(proton_dir):
                if dir_name.startswith("GE-Proton"):
                    version = re.search(r"GE-Proton(\d+-\d+)", dir_name)
                    if version:
                        version_str = version.group(1)
                        if latest_version is None or version_str > latest_version:
                            latest_version = version_str
                            if not get_path:
                                tool_version = dir_name
                            else:
                                tool_version = os.path.join(proton_dir, dir_name)

    return tool_version 

def get_latest_proton(get_path=False):

    latest_stable_version = None
    latest_stable_tool = None
    experimental_tool = None

    for proton_dir in PROTON_DIRS:
        if os.path.exists(proton_dir):
            for dir_name in os.listdir(proton_dir):
                if dir_name.startswith("Proton -"):
                    version = re.search(r"Proton - (\d+\.\d+)", dir_name)
                    if version:
                        version_str = version.group(1)
                        if not dir_name.endswith("Experimental"):
                            if latest_stable_version is None or version_str > latest_stable_version:
                                latest_stable_version = version_str
                                if not get_path:
                                    latest_stable_tool = dir_name
                                else:
                                    latest_stable_tool = os.path.join(proton_dir, dir_name)

                        else:
                            if not get_path:
                                experimental_tool = dir_name
                            else:
                                experimental_tool = os.path.join(proton_dir, dir_name)

    if latest_stable_tool:
        return latest_stable_tool
    elif experimental_tool:
        return experimental_tool
    else:
        return None
    
def get_proton_version(get_path=False):
    version = get_latest_proton_ge(get_path)
    if not version:
        version = get_latest_proton(get_path)
    return version

