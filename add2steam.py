import os
import json
import subprocess
import requests
import logging
import sys
import struct
import concurrent.futures
import vdf
'''
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QPushButton, 
                              QLabel, QScrollArea, QWidget, QMessageBox)
from PySide6.QtCore import Qt
'''
from urllib.parse import quote
from icon_extractor import extract_icon
from identify_game import GameMatcher, add_files_to_user_selected

from config import (SCRIPT_DIR, STEAM_ID_MAPPING_FILE, STEAM_USERDATA_DIR, SHORTCUTS_FILE, DEFAULT_GAMES_INFO_PATH, USER_MAPPING_PATH, 
                    CONFIG_VDF_PATH, get_current_user, generate_app_id, generate_short_app_id,
                    generate_shortcut_id, get_proton_version, get_steam_username)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(str(SCRIPT_DIR / "no_steam_to_steam.log")),
        logging.StreamHandler()
    ]
)

def save_steam_id_mapping(steam_id_mapping):
    try:
        existing_mapping = {}
        if os.path.exists(STEAM_ID_MAPPING_FILE):
            with open(STEAM_ID_MAPPING_FILE, "r") as f:
                existing_mapping = json.load(f)
        
        if steam_id_mapping:
            existing_mapping.update(steam_id_mapping)
            
            with open(STEAM_ID_MAPPING_FILE, "w") as f:
                json.dump(existing_mapping, f, indent=4)
            
            logging.info("Game-steam_id mapping updated in steam_id_mapping.json")
        else:
            logging.info("No new games found to update.")
    except Exception as e:
        logging.error(f"Error saving game-steam_id mapping: {e}")

def process_user_selected_games(json_file):
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            games_data = json.load(f)

        needs_processing = any(
            game.get("user_selected", False) and "files" not in game
            for game in games_data.values()
        )

        if needs_processing:
            matcher = GameMatcher()

            updated_games_data = add_files_to_user_selected(games_data, matcher)

            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(updated_games_data, f, ensure_ascii=False, indent=4)

            logging.info("'files' field added to manually selected games.")
        else:
            logging.info("No manually selected games found that require processing.")

    except Exception as e:
        logging.error(f"Error processing manually selected games: {e}")
        sys.exit(1)

def load_games(json_file):
    try:
        with open(json_file, "r") as f:
            data = json.load(f)
        
        if "games" in data and isinstance(data["games"], list) and not data["games"]:
            del data["games"]
        
        games = {key: value for key, value in data.items() if isinstance(value, dict) and "name" in value and "exe_path" in value}
        
        if not games:
            logging.error("No valid games found in the JSON file.")
            sys.exit(1)
        
        return games
    except Exception as e:
        logging.error(f"Error loading JSON file: {e}")
        sys.exit(1)

def save_user_mapping(user_mapping):
    try:
        with open(USER_MAPPING_PATH, "w") as f:
            json.dump(user_mapping, f, indent=4)
        logging.info(f"User-ID mapping saved in {USER_MAPPING_PATH}")
    except Exception as e:
        logging.error(f"Error saving user-ID mapping: {e}")

def select_steam_user():
    try:
        user_folders = [
            f for f in os.listdir(STEAM_USERDATA_DIR)
            if os.path.isdir(os.path.join(STEAM_USERDATA_DIR, f)) and f != "0"
        ]

        if not user_folders:
            subprocess.run(['zenity', '--error', 
                          '--title=Error', 
                          '--text=Steam user folder not found.'],
                          check=True)
            return None

        current_user = get_current_user()
        user_mapping = {}
        
        zenity_args = [
            'zenity',
            '--list',
            '--title=Select Steam User',
            '--text=Select a user:',
            '--radiolist',
            '--column=Select',
            '--column=User ID',
            '--column=Name',
            '--width=500',
            '--height=300',
            '--extra-button=All users',
            '--cancel-label=Cancel'
        ]

        for user_id in user_folders:
            username = get_steam_username(user_id)
            user_mapping[user_id] = username
            display_name = f"{username} (current)" if user_id == current_user else username
            
            zenity_args.extend(['FALSE', user_id, display_name])

        save_user_mapping(user_mapping)

        result = subprocess.run(zenity_args, 
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              text=True)

        if result.returncode == 1:
            return None
            
        output = result.stdout.strip()
        
        if output == "All users":
            return "all"
        elif output:
            return output 
        return None

    except Exception as e:
        logging.error(f"Error selecting user: {e}")
        subprocess.run(['zenity', '--error',
                       '--title=Error',
                       f'--text=Error selecting user: {str(e)}'],
                       check=True)
        return None

'''
def select_steam_user(STEAM_USERDATA_DIR, get_current_user, get_steam_username, save_user_mapping):
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    try:
        user_folders = [
            f for f in os.listdir(STEAM_USERDATA_DIR)
            if os.path.isdir(os.path.join(STEAM_USERDATA_DIR, f)) and f != "0"
        ]

        if not user_folders:
            QMessageBox.critical(None, "Error", "Steam user folder not found.")
            return None

        current_user = get_current_user()
        user_mapping = {}
        selected_user = [None]  # Using list to allow modification in nested function

        # Create dialog
        dialog = QDialog()
        dialog.setWindowTitle("Select Steam User")
        dialog.setMinimumSize(600, 400)  # Larger size for Steam Deck touch screen

        # Main layout
        layout = QVBoxLayout(dialog)
        
        # Add label
        label = QLabel("Select a Steam user:")
        label.setStyleSheet("font-size: 18px;")
        layout.addWidget(label)

        # Create scroll area for buttons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setAlignment(Qt.AlignTop)
        
        # Add user buttons
        for user_id in user_folders:
            username = get_steam_username(user_id)
            user_mapping[user_id] = username
            
            display_name = f"{username} (current user)" if user_id == current_user else username
            
            btn = QPushButton(display_name)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 20px;
                    font-size: 16px;
                    text-align: left;
                    margin: 5px;
                    min-height: 40px;
                }
            """)
            btn.clicked.connect(lambda _, uid=user_id: select_user(uid))
            scroll_layout.addWidget(btn)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Add "All users" button
        all_users_btn = QPushButton("All users")
        all_users_btn.setStyleSheet("""
            QPushButton {
                padding: 20px;
                font-size: 16px;
                font-weight: bold;
                margin: 5px;
                min-height: 40px;
                background-color: #2a475e;
                color: white;
            }
        """)
        all_users_btn.clicked.connect(lambda: select_user("all"))
        layout.addWidget(all_users_btn)

        def select_user(user_id):
            selected_user[0] = user_id
            dialog.accept()

        # Save user mapping
        save_user_mapping(user_mapping)

        # Center dialog on screen
        dialog.move(QApplication.primaryScreen().availableGeometry().center() - dialog.rect().center())
        
        # Show dialog
        dialog.exec()
        return selected_user[0]

    except Exception as e:
        logging.error(f"Error selecting Steam user: {e}")
        QMessageBox.critical(None, "Error", f"An error occurred: {str(e)}")
        return None
'''

def download_image(url, path):
    if not url:
        logging.warning(f"Empty image URL for {path}")
        return False
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(path, "wb") as f:
                f.write(response.content)
            return True
        else:
            logging.warning(f"Could not download image from {url}. Status code: {response.status_code}")
    except Exception as e:
        logging.error(f"Error downloading image from {url}: {e}")
    return False

def get_steam_images(app_id):
    """
    Gets image URLs from Steam CDN.
    """
    base_url = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}"
    return {
        "header": f"{base_url}/header.jpg",         
        "library_hero": f"{base_url}/library_hero.jpg", 
        "logo": f"{base_url}/logo.png",  
        "library_600x900": f"{base_url}/library_600x900.jpg", 
    }

def get_thegamesdb_images(game_name):
    search_url = f"https://api.thegamesdb.net/v1/Games/ByGameName?name={quote(game_name)}"
    try:
        response = requests.get(search_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("data", {}).get("games"):
                game_id = data["data"]["games"][0]["id"]
                images_url = f"https://api.thegamesdb.net/v1/Games/Images?games_id={game_id}"
                images_response = requests.get(images_url, timeout=10)
                if images_response.status_code == 200:
                    images_data = images_response.json().get("data", {}).get("images", {})
                    return {
                        "header": images_data.get("boxart", {}).get("front", ""),
                        "library_hero": images_data.get("fanart", ""),  
                        "logo": images_data.get("clearlogo", ""),   
                        "library_600x900": images_data.get("boxart", {}).get("front", ""),
                        "icon": images_data.get("icon", "") or images_data.get("clearlogo", ""), 
                    }
    except Exception as e:
        logging.error(f"Error getting images from TheGamesDB for {game_name}: {e}")
    return {}

def save_grid_images(app_id_short, USER_CONFIG_DIR, game_data, bigpicture_appid=None, exe_path=None):
    grid_path = os.path.join(USER_CONFIG_DIR, "grid")
    icons_path = os.path.join(USER_CONFIG_DIR, "icons")
    os.makedirs(grid_path, exist_ok=True)
    os.makedirs(icons_path, exist_ok=True)

    steam_appid = next((p["id"] for p in game_data.get("providers", []) if p["service"] == "steam"), None)

    lutris_images = {
        "header": game_data.get("banner_url", ""),
        "coverart": game_data.get("coverart", ""),
        "icon_url": game_data.get("icon_url", ""),
    }

    steam_images = get_steam_images(steam_appid) if steam_appid else {}

    thegamesdb_images = {}
    if not all(steam_images.values()):
        thegamesdb_images = get_thegamesdb_images(game_data["name"])

    image_mapping = {
        "header": steam_images.get("header") or thegamesdb_images.get("header") or lutris_images.get("banner_url", ""),
        "library_hero": steam_images.get("library_hero") or thegamesdb_images.get("library_hero", ""),
        "logo": steam_images.get("logo") or thegamesdb_images.get("logo", ""),
        "library_600x900": steam_images.get("library_600x900") or thegamesdb_images.get("library_600x900", "") or lutris_images.get("coverart", ""),
        "icon": thegamesdb_images.get("icon", "") or lutris_images.get("icon_url", ""),
    }

    def get_icon_extension(icon_url):
        if not icon_url:
            return None
        if icon_url.lower().endswith('.ico'):
            return 'ico'
        return 'png'

    icon_extension = get_icon_extension(image_mapping["icon"])
    icon_filename = f"{app_id_short}.{icon_extension}" if icon_extension else None
    icon_path = os.path.join(icons_path, icon_filename) if icon_filename else None

    image_files = {
        "header": os.path.join(grid_path, f"{app_id_short}.jpg"),
        "library_600x900": os.path.join(grid_path, f"{app_id_short}p.jpg"),
        "library_hero": os.path.join(grid_path, f"{app_id_short}_hero.jpg"),
        "logo": os.path.join(grid_path, f"{app_id_short}_logo.png"),
        "icon": icon_path,
    }

    logging.info(f"Checking images for {game_data['name']}")

    if image_mapping["icon"] and icon_path:
        if image_mapping["icon"].startswith(('http://', 'https://')):
            if not os.path.exists(icon_path):
                if not download_image(image_mapping["icon"], icon_path):
                    icon_path = os.path.join(icons_path, f"{app_id_short}.ico")
                    if exe_path and extract_icon(exe_path, icon_path):
                        logging.info(f"Icon extracted from executable for {game_data['name']}")
                        image_mapping["icon"] = icon_path
                        image_files["icon"] = icon_path
                    else:
                        image_mapping["icon"] = ""
                else:
                    image_mapping["icon"] = icon_path
            else:
                image_mapping["icon"] = icon_path
        else:
            image_mapping["icon"] = image_mapping["icon"] if os.path.exists(image_mapping["icon"]) else ""
    elif exe_path:
        icon_path = os.path.join(icons_path, f"{app_id_short}.ico")
        if extract_icon(exe_path, icon_path):
            image_mapping["icon"] = icon_path
            image_files["icon"] = icon_path

    download_tasks = []
    for key, url in image_mapping.items():
        if not url or key == "icon":  
            continue
            
        target_path = image_files[key]
        
        if os.path.exists(target_path):
            continue
            
        if url.startswith(('http://', 'https://')):
            download_tasks.append((url, target_path))
            
            if bigpicture_appid and key in ["library_hero", "library_600x900"]:
                bigpicture_image_name = f"{bigpicture_appid}_hero.jpg" if key == "library_hero" else f"{bigpicture_appid}p.jpg"
                bigpicture_image_path = os.path.join(grid_path, bigpicture_image_name)
                if not os.path.exists(bigpicture_image_path):
                    download_tasks.append((url, bigpicture_image_path))

    if download_tasks:
        logging.info(f"Downloading {len(download_tasks)} images for {game_data['name']}")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_url = {executor.submit(download_image, url, path): (url, path) for url, path in download_tasks}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url, path = future_to_url[future]
                try:
                    if not future.result():
                        logging.error(f"Error downloading {url}")
                except Exception as e:
                    logging.error(f"Unexpected error downloading {url}: {e}")
    else:
        logging.info(f"All images for {game_data['name']} already exist")

    for key in image_mapping:
        if key in image_files and os.path.exists(image_files[key]):
            image_mapping[key] = image_files[key]

    return image_mapping

def read_type(reader):
    return reader.read(1)

def read_string(reader):
    buffer = []
    while True:
        char = reader.read(1)
        if (char == b'\x00'):
            break
        buffer.append(char)
    return b''.join(buffer).decode('utf-8')

def read_int(reader):
    return struct.unpack('<I', reader.read(4))[0]

def read_object(reader):
    result = {}
    while True:
        type_byte = read_type(reader)
        if type_byte == b'\x08':  # VdfType.ObjectEnd
            break
        name = read_string(reader)
        if type_byte == b'\x00':  # VdfType.Object
            result[name] = read_object(reader)
        elif type_byte == b'\x01':  # VdfType.String
            result[name] = read_string(reader)
        elif type_byte == b'\x02':  # VdfType.Int
            result[name] = read_int(reader)
        else:
            raise ValueError(f"Unknown type: {type_byte.hex()}")
    return result

def write_type(writer, value):
    writer.write(value)

def write_string(writer, value):
    writer.write(value.encode('utf-8'))
    writer.write(b'\x00')

def write_int(writer, value):
    writer.write(struct.pack("<I", value & 0xFFFFFFFF)) 

def write_object(writer, value):
    for name, sub_object in value.items():
        if isinstance(sub_object, dict):
            write_type(writer, b'\x00')  # VdfType.Object
            write_string(writer, name)
            write_object(writer, sub_object)
        elif isinstance(sub_object, str):
            write_type(writer, b'\x01')  # VdfType.String
            write_string(writer, name)
            write_string(writer, sub_object)
        elif isinstance(sub_object, int):
            write_type(writer, b'\x02')  # VdfType.Int
            write_string(writer, name)
            write_int(writer, sub_object)
    write_type(writer, b'\x08')  # VdfType.ObjectEnd

def load_shortcuts(path):
    if not os.path.exists(path):
        return {}
    else:
        with open(path, 'rb') as f:
            return read_object(f).get('shortcuts', {})

def get_valid_shortcuts(shortcuts_path):
    all_shortcuts = load_shortcuts(shortcuts_path)
    valid_shortcuts = {}
    removed_count = 0
    
    for key, value in all_shortcuts.items():
        exe_path = value.get('Exe', '').strip('"')
        if os.path.exists(os.path.expanduser(exe_path)):
            valid_shortcuts[key] = value
        else:
            removed_count += 1
    
    return valid_shortcuts, removed_count

def reindex_shortcuts_alphabetically(shortcuts):
    sorted_shortcuts = sorted(shortcuts.items(),
                            key=lambda x: x[1].get('appname', '').lower())
    
    reindexed = {}
    for new_index, (old_index, shortcut_data) in enumerate(sorted_shortcuts):
        reindexed[str(new_index)] = shortcut_data
    
    logging.info(f"Reindexed {len(reindexed)} shortcuts alphabetically")
    return reindexed

def save_shortcuts(path, shortcuts):
    try:
        backup_path = path + "_old"
        if os.path.exists(path):
            os.rename(path, backup_path)

        with open(path, "wb") as f:
            write_object(f, {"shortcuts": shortcuts})
        logging.info(f"shortcuts.vdf file updated successfully")

        if os.path.exists(backup_path):
            os.remove(backup_path)
            
    except Exception as e:
        logging.error(f"Error saving: {e}")
        if os.path.exists(backup_path):
            os.rename(backup_path, path)
        sys.exit(1)

def add_entry(shortcuts, input_tuple):
    entry_id = input_tuple[13][0]
    shortcuts[entry_id] = {
        'appid': int(input_tuple[0]),
        'appname': input_tuple[1],
        'Exe': input_tuple[2],
        'StartDir': input_tuple[3],
        'icon': input_tuple[4],
        'ShortcutPath': input_tuple[5],
        'LaunchOptions': input_tuple[6],
        'IsHidden': int(input_tuple[7]),
        'AllowDesktopConfig': int(input_tuple[8]),
        'AllowOverlay': int(input_tuple[9]),
        'OpenVR': int(input_tuple[10]),
        'Devkit': 0,
        'DevkitGameID': '',
        'DevkitOverrideAppID': 0,
        'LastPlayTime': 0,
        'FlatpakAppID': '',
        'tags': {}
    }

def input_preparation(args, entry_index):
    var_appid = str(args[0])  
    var_app_name = args[1]
    var_path = f'"{args[2]}"'  
    var_start_dir = args[3]    
    var_icon_path = args[4]   
    var_shortcut_path = args[5]
    var_launch_options = args[6]

    var_is_hidden = '1' if args[7] == '1' else '0'
    var_allow_desk_conf = '1' if args[8] == '1' else '0'
    var_allow_overlay = '1' if args[9] == '1' else '0'
    var_open_vr = '1' if args[10] == '1' else '0'

    var_last_play_time = '0'
    var_tags = ''

    return (var_appid, var_app_name, var_path, var_start_dir, var_icon_path,
            var_shortcut_path, var_launch_options, var_is_hidden, var_allow_desk_conf,
            var_allow_overlay, var_open_vr, var_last_play_time, var_tags, entry_index)

def game_exists(shortcuts_path, exe_path):
    normalized_exe_path = os.path.normcase(os.path.normpath(exe_path)).encode('utf-8')
    if os.path.exists(shortcuts_path):
        try:
            with open(shortcuts_path, 'rb') as f:
                content = f.read()
                return normalized_exe_path in content
        except Exception as e:
            logging.error(f"Error reading shortcuts.vdf file: {e}")
            return False

def find_entry_index(shortcuts):
    if not shortcuts:
        return '0', 0
    entry_index = max(int(key) for key in shortcuts.keys())+1
    return str(entry_index), entry_index

def set_proton_compat_tool(short_appid, compat_tool):
    try:
        if not os.path.exists(CONFIG_VDF_PATH):
            logging.error(f"File {CONFIG_VDF_PATH} does not exist.")
            return

        with open(CONFIG_VDF_PATH, "r", encoding="utf-8") as f:
            config_data = vdf.load(f)
        
        if "InstallConfigStore" not in config_data:
            config_data["InstallConfigStore"] = {}
        if "Software" not in config_data["InstallConfigStore"]:
            config_data["InstallConfigStore"]["Software"] = {}
        if "Valve" not in config_data["InstallConfigStore"]["Software"]:
            config_data["InstallConfigStore"]["Software"]["Valve"] = {}
        if "Steam" not in config_data["InstallConfigStore"]["Software"]["Valve"]:
            config_data["InstallConfigStore"]["Software"]["Valve"]["Steam"] = {}
        if "CompatToolMapping" not in config_data["InstallConfigStore"]["Software"]["Valve"]["Steam"]:
            config_data["InstallConfigStore"]["Software"]["Valve"]["Steam"]["CompatToolMapping"] = {}
        
        config_data["InstallConfigStore"]["Software"]["Valve"]["Steam"]["CompatToolMapping"][str(short_appid)] = {
            "name": compat_tool,
            "config": "",
            "priority": "250"
        }

        with open(CONFIG_VDF_PATH, "w", encoding="utf-8") as f:
            vdf.dump(config_data, f, pretty=True)
        
        logging.info(f"Proton configuration updated for {short_appid}.")
    except Exception as e:
        logging.error(f"Error setting Proton in config.vdf: {e}")

def add_games_to_shortcuts(games, user_id):
    USER_CONFIG_DIR = os.path.join(STEAM_USERDATA_DIR, user_id, "config")
    shortcuts_path = os.path.join(USER_CONFIG_DIR, SHORTCUTS_FILE)

    valid_shortcuts, removed_count = get_valid_shortcuts(shortcuts_path)
    shortcuts = reindex_shortcuts_alphabetically(valid_shortcuts)

    steam_id_mapping = {}
    games_added = 0
    games_updated = 0

    try:
        for game_folder, game_data in games.items():
            exe_path = game_data.get("exe_path", "")
            if not os.path.exists(exe_path):
                continue
            
            game_name = game_data["name"]
            steam_app_id = next((p["id"] for p in game_data.get("providers", []) if p["service"] == "steam"), None)
            app_id_long = generate_app_id(game_data["exe_path"], game_name)
            app_id_short = generate_short_app_id(game_data["exe_path"], game_name)
            shortcut_id = generate_shortcut_id(game_data["exe_path"], game_name)
            
            steam_id_mapping[game_name] = {
                "app_id_long": app_id_long,
                "app_id_short": app_id_short,
                "shortcut_id": shortcut_id,
                "exe_path": game_data["exe_path"],
                "files": game_data["files"],
                "install_dir": game_folder,
                "steam_app_id": steam_app_id,
            }

            image_updated = save_grid_images(app_id_short, USER_CONFIG_DIR, game_data, app_id_long, exe_path)
            if image_updated:
                games_updated += 1

            if game_exists(shortcuts_path, game_data["exe_path"]):
                continue

            entry_index = find_entry_index(shortcuts)

            icon_name = f"{app_id_short}.ico"
            icon_path = os.path.join(USER_CONFIG_DIR, "icons", icon_name)
            if not os.path.exists(icon_path):
                icon_name = f"{app_id_short}.png"
                icon_path = os.path.join(USER_CONFIG_DIR, "icons", icon_name)

            game_data["icon"] = icon_path

            input_tuple = input_preparation([
                str(shortcut_id), game_data["name"], game_data["exe_path"], os.path.dirname(game_data["exe_path"]),
                game_data["icon"], "", "", "1", "1", "0", "0", "0"
            ], entry_index)
            add_entry(shortcuts, input_tuple)

            games_added += 1

            set_proton_compat_tool(app_id_short, get_proton_version())

        save_shortcuts(shortcuts_path, shortcuts)
            
        logging.info(f"Summary: {games_added} games added, {games_updated} games updated (images), {removed_count} games removed (executables not found)")
    except Exception as e:
        logging.error(f"Error processing shortcuts.vdf file: {e}")
        sys.exit(1)

    return steam_id_mapping

def main(json_file = DEFAULT_GAMES_INFO_PATH):
    logging.info("Starting script...")

    if not os.path.exists(json_file):
        logging.error(f"JSON file does not exist: {json_file}")
        sys.exit(1)

    process_user_selected_games(json_file)

    games = load_games(json_file)
    logging.info(f"Loaded {len(games)} games from JSON file.")

#    selected_user = select_steam_user(STEAM_USERDATA_DIR, get_current_user, get_steam_username, save_user_mapping)
#    selected_user = select_steam_user()
    selected_user = get_current_user()
    if not selected_user:
        sys.exit(1)

    if selected_user == "all":
        user_folders = [
            f for f in os.listdir(STEAM_USERDATA_DIR)
            if os.path.isdir(os.path.join(STEAM_USERDATA_DIR, f)) and f != "0"
        ]
    else:
        user_folders = [selected_user]

    steam_id_mapping = {}

    for user_id in user_folders:
        logging.info(f"Processing user: {user_id}")
        user_steam_id_mapping = add_games_to_shortcuts(games, user_id)
        steam_id_mapping.update(user_steam_id_mapping)

    save_steam_id_mapping(steam_id_mapping)
    logging.info("Script finished successfully.")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        json_file = DEFAULT_GAMES_INFO_PATH
    else:
        json_file = sys.argv[1]

    if not os.path.exists(json_file):
        logging.error(f"JSON file does not exist: {json_file}")
        sys.exit(1)

    main(json_file)
