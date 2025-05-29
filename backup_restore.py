import logging
import os
import shutil
import subprocess
import py7zr 
from pathlib import Path
import xml.etree.ElementTree as ET
import json
from datetime import datetime
from fnmatch import fnmatch


from config import DEFAULT_BACKUPS_PATH, ID_MAP_PATH, INVENTORY_FILE, SYNC_RECORD_FILE, get_backups_directory
from utils import compute_hash

logger = logging.getLogger('GBM_Backup')

def load_games_mapping(path_id_map=ID_MAP_PATH):
    try:
        with open(path_id_map, 'r') as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Error loading JSON file: {e}")
        return None

def generate_games_inventory(backups_path=DEFAULT_BACKUPS_PATH, inventory_path=INVENTORY_FILE):
    inventory = {}

    for folder in backups_path.iterdir():
        if not folder.is_dir():
            continue

        files_7z = [f for f in folder.iterdir() 
                    if f.is_file() and f.suffix.lower() == '.7z']
        
        if not files_7z:
            logger.warning(f"Warning: No .7z files found in {folder.name}")
            continue

        backups_metadata = []
        for file_7z in files_7z:
            metadata = load_metadata_from_7z(file_7z)
            if metadata and "game_name" in metadata and "original_path" in metadata:
                backups_metadata.append({
                    "file": file_7z.name,
                    "metadata": metadata,
                    "timestamp": file_7z.stat().st_mtime
                })

        if not backups_metadata:
            logger.warning(f"Warning: No valid metadata found in {folder.name}")
            continue

        backups_metadata.sort(key=lambda x: x["timestamp"], reverse=True)

        game_name = backups_metadata[0]["metadata"]["game_name"]
        
        game_entry = {
            "folder": str(folder.name),
            "executable": backups_metadata[0]["metadata"].get("process_name", ""),
            "most_recent_7z_file": backups_metadata[0]["file"],
            "7z_files": {
                b["file"]: {
                    "original_path": b["metadata"]["original_path"],
                    "modification_date": datetime.fromtimestamp(b["timestamp"]).isoformat()
                }
                for b in backups_metadata
            }
        }

        if game_name not in inventory:
            inventory[game_name] = []
        
        inventory[game_name].append(game_entry)

    try:
        with open(inventory_path, "w", encoding='utf-8') as file:
            json.dump(inventory, file, indent=4, ensure_ascii=False)
        logger.info(f"Inventory generated and saved to {inventory_path}")
        return inventory
    except Exception as e:
        logger.error(f"Error saving inventory: {str(e)}")
        return False

def load_games_backup_inventory(inventory_path=INVENTORY_FILE):
    backups_path = get_backups_directory()
    try:
        if not Path(inventory_path).exists() or file_needs_update(inventory_path):
            logger.info(f"Inventory file doesn't exist or is outdated. Generating inventory...")
            if not generate_games_inventory(backups_path=backups_path, inventory_path=inventory_path):
                return None

        with open(inventory_path, "r") as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Error loading or generating inventory file: {e}")
        return None

def file_needs_update(file_path, days_threshold=7):
    try:
        modification_date = datetime.fromtimestamp(Path(file_path).stat().st_mtime)
        current_date = datetime.now()

        days_diff = (current_date - modification_date).days

        return days_diff > days_threshold
    except FileNotFoundError:
        return True
    except Exception as e:
        logger.error(f"Error checking file age: {e}")
        return True

def show_backup_selection_dialog(backups_info):
    try:
        if not backups_info:
            return -1

        zenity_list = []
        default_option = 0
        
        for i, backup in enumerate(backups_info):
            is_recent = backup.get("most_recent", False)
            recent_text = " (MOST RECENT)" if is_recent else ""
            
            backup_text = (
                f"File: {backup['file'].name}{recent_text}\n"
                f"Folder: {backup['folder']}\n"
                f"Original path: {backup['original_path']}\n"
                f"Last modification: {backup['modification_date']}\n"
            )
            
            zenity_list.append("TRUE" if is_recent else "FALSE")
            zenity_list.append(str(i))  
            zenity_list.append(backup_text.replace('"', "'")) 
            
            if is_recent:
                default_option = i

        cmd = [
            'zenity',
            '--list',
            '--title=Backup Selection',
            '--text=Multiple backups found for the same path. Select which one to keep:',
            '--radiolist',
            '--column=Select',
            '--column=ID',
            '--column=Backup Information',
            '--width=800',
            '--height=600',
            '--ok-label=OK',
            '--cancel-label=Cancel'
        ] + zenity_list

        result = subprocess.run(cmd, 
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True)

        if result.returncode == 1:  
            return -1

        selected_id = result.stdout.strip()
        if selected_id:
            return int(selected_id)
        return default_option

    except Exception as e:
        logging.error(f"Error in backup selection dialog: {e}")
        subprocess.run([
            'zenity',
            '--error',
            '--title=Error',
            f'--text=Error selecting backup: {str(e)}'
        ], check=True)
        return -1

def find_backups(game_name, inventory, record, backups_path=DEFAULT_BACKUPS_PATH):
    if game_name not in inventory:
        logger.info(f"No backups found for {game_name} in inventory.")
        return None
    
    all_backups = []
    for entry in inventory[game_name]:
        folder = entry["folder"]
        folder_path = backups_path / folder
        
        if not folder_path.exists():
            logger.warning(f"Warning: Folder {folder} doesn't exist.")
            continue
        
        for file, metadata in entry["7z_files"].items():
            file_path = folder_path / file
            if file_path.exists():
                all_backups.append({
                    "file": file_path,
                    "str_path": str(file_path), 
                    "folder": folder,
                    "original_path": metadata["original_path"],
                    "modification_date": metadata["modification_date"],
                    "timestamp": datetime.fromisoformat(metadata["modification_date"]).timestamp()
                })
    
    if not all_backups:
        logger.info(f"No valid .7z files found for {game_name}")
        return None
    
    if len(all_backups) == 1:
        return [all_backups[0]["file"]]
    
    backups_by_path = {}
    chosen_backups = []
    
    for backup in all_backups:
        path = backup["original_path"]
        if path not in backups_by_path:
            backups_by_path[path] = []
        backups_by_path[path].append(backup)
    
    for path, backups in backups_by_path.items():
        if len(backups) == 1:
            chosen_backups.append(backups[0]["file"])
            continue
        
        record_backups = [
            b for b in backups 
            if game_name in record and str(b["str_path"]) in record[game_name]
        ]
        
        if record_backups:
            recorded_backups_sorted = sorted(
                record_backups, 
                key=lambda x: x["timestamp"], 
                reverse=True
            )
            chosen_backups.append(recorded_backups_sorted[0]["file"])
            logger.info(f"Automatic selection: {recorded_backups_sorted[0]['file'].name} (already registered)")
            continue
        
        backups_sorted = sorted(backups, key=lambda x: x["timestamp"], reverse=True)
        for i, backup in enumerate(backups_sorted):
            backup["most_recent"] = (i == 0)
        
        selected_idx = show_backup_selection_dialog(backups_sorted)
        if selected_idx == -1:
            return None
        
        chosen_backups.append(backups_sorted[selected_idx]["file"])
    
    return chosen_backups

def load_metadata_from_7z(file_path_7z):
    try:
        with py7zr.SevenZipFile(file_path_7z, mode='r') as file_7z:
            file_7z.extract(targets=["_gbm_backup_metadata.xml"])

        with open("_gbm_backup_metadata.xml", "r", encoding="utf-8") as file_xml:
            tree = ET.parse(file_xml)
            root = tree.getroot()

            game_name = root.findtext(".//GameData/Name")
            original_path = root.findtext(".//GameData/Path")
            if not game_name or not original_path:
                logger.info(f"Error: Metadata file doesn't contain required information.")
                return None

            metadata = {
                "game_name": game_name,
                "original_path": original_path,
                "folder_save": root.findtext(".//GameData/FolderSave"),
                "process_name": root.findtext(".//GameData/ProcessName"),
            }
            return metadata
    except Exception as e:
        logger.info(f"Error reading metadata file: {e}")
        return None
    finally:
        if os.path.exists("_gbm_backup_metadata.xml"):
            os.remove("_gbm_backup_metadata.xml")

def _copy_folder_7z(file_path_7z, destination_path):
    try:
        Path(destination_path).mkdir(parents=True, exist_ok=True)
        
        with py7zr.SevenZipFile(file_path_7z, mode='r') as file_7z:
            file_7z.extractall(path=destination_path)
        
        metadata_path = Path(destination_path) / "_gbm_backup_metadata.xml"
        if metadata_path.exists():
            metadata_path.unlink()
            
        if not any(Path(destination_path).iterdir()):
            logger.error(f"7z file {file_path_7z} is empty or contains no valid data")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error extracting {file_path_7z}: {str(e)}")
        if Path(destination_path).exists():
            shutil.rmtree(destination_path, ignore_errors=True)
        return False

def _copy_file_7z(file_path_7z, destination_file_path):
    try:
        Path(destination_file_path).parent.mkdir(parents=True, exist_ok=True)
        
        temp_dir = Path("temp_extract")
        temp_dir.mkdir(exist_ok=True)
        
        with py7zr.SevenZipFile(file_path_7z, mode='r') as file_7z:
            file_7z.extractall(path=temp_dir)
        
        valid_files = [
            f for f in temp_dir.rglob('*') 
            if f.is_file() and f.name != "_gbm_backup_metadata.xml"
        ]
        
        if not valid_files:
            logger.error(f"No valid files found in {file_path_7z}")
            return False
        
        temp_file = valid_files[0]
        shutil.move(str(temp_file), str(destination_file_path))
        
        return True
        
    except Exception as e:
        logger.error(f"Error copying file from {file_path_7z}: {str(e)}")
        return False
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

def copy_saves(file_path_7z, destination_path, is_folder=True):
    logger.info(f"Starting copy from {file_path_7z} to {destination_path}")
    
    if is_folder:
        result = _copy_folder_7z(file_path_7z, destination_path)
    else:
        result = _copy_file_7z(file_path_7z, destination_path)
    
    return result

def load_sync_record(record_path=SYNC_RECORD_FILE):
    try:
        if Path(record_path).exists():
            with open(record_path, "r") as file:
                return json.load(file)
        else:
            return {}
    except Exception as e:
        logger.info(f"Error loading sync record: {e}")
        return {}

def save_sync_record(record, record_path=SYNC_RECORD_FILE):
    try:
        with open(record_path, "w") as file:
            json.dump(record, file, indent=4)
    except Exception as e:
        logger.info(f"Error saving sync record: {e}")

def get_files_date(path):
    if not path.exists():
        return None

    if path.is_file():
        return datetime.fromtimestamp(path.stat().st_mtime)

    most_recent_date = None
    for file in path.rglob("*"):
        if file.is_file():
            modification_date = datetime.fromtimestamp(file.stat().st_mtime)
            if not most_recent_date or modification_date > most_recent_date:
                most_recent_date = modification_date

    return most_recent_date

def update_backup(file_path_7z, steamdeck_path, metadata=None):
    try:
        temp_dir = Path("temp_steamdeck")
        temp_dir.mkdir(parents=True, exist_ok=True)

        is_folder = metadata.get('folder_save', True) if metadata else True
        file_type = metadata.get('FileType', '') if metadata else ''

        if is_folder:
            if not steamdeck_path.exists():
                raise ValueError(f"Path not found: {steamdeck_path}")

            for file in steamdeck_path.rglob("*"):
                if file.is_file():
                    relative_path = file.relative_to(steamdeck_path)
                    destination_path = temp_dir / relative_path
                    destination_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, destination_path)
        else:
            if file_type:
                files_to_copy = process_filetype(steamdeck_path, file_type)
                if not files_to_copy:
                    raise ValueError(f"No files matching: {file_type}")

                for file in files_to_copy:
                    relative_path = file.relative_to(steamdeck_path.parent if steamdeck_path.is_dir() else steamdeck_path)
                    destination_path = temp_dir / relative_path
                    destination_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, destination_path)
            else:
                if not steamdeck_path.is_file():
                    raise ValueError(f"File not found: {steamdeck_path}")
                shutil.copy2(steamdeck_path, temp_dir / steamdeck_path.name)

        with py7zr.SevenZipFile(file_path_7z, mode='a') as file_7z:
            for file in temp_dir.rglob("*"):
                if file.is_file():
                    path_7z = file.relative_to(temp_dir)
                    file_7z.write(file, str(path_7z).replace('\\', '/'))

        logger.info(f"✅ Backup updated successfully: {file_path_7z}")
        return True

    except Exception as e:
        logger.error(f"❌ Error updating backup: {str(e)}")
        return False
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

def process_filetype(base_path, file_type):
    matching_files = []
    
    if base_path.is_dir():
        base_dir = base_path
    else:
        base_dir = base_path.parent

    patterns = [p.strip() for p in file_type.split(':') if p.strip()]
    
    for pattern in patterns:
        if ':' in pattern and '*' not in pattern:
            file, subdir = pattern.split(':', 1)
            search_path = base_dir / subdir.strip()
            if (search_path / file.strip()).is_file():
                matching_files.append(search_path / file.strip())
            continue
        
        for file in base_dir.rglob(pattern):
            if file.is_file() and fnmatch(file.name, pattern.split('/')[-1]):
                matching_files.append(file)
    
    return list(set(matching_files))

def show_sync_conflict_dialog(game_name, backup_date, steamdeck_date, 
                            hash_backup, hash_local, hash_backup_record, 
                            hash_local_record):
    try:
        if backup_date > steamdeck_date:
            text_backup = f"Backup (newer: {backup_date.strftime('%Y-%m-%d %H:%M:%S')}"
            text_local = f"Local save (older: {steamdeck_date.strftime('%Y-%m-%d %H:%M:%S')}"
        elif steamdeck_date > backup_date:
            text_backup = f"Backup (older: {backup_date.strftime('%Y-%m-%d %H:%M:%S')}"
            text_local = f"Local save (newer: {steamdeck_date.strftime('%Y-%m-%d %H:%M:%S')})"
        else:
            text_backup = f"Backup (same date: {backup_date.strftime('%Y-%m-%d %H:%M:%S')})"
            text_local = f"Local save (same date: {steamdeck_date.strftime('%Y-%m-%d %H:%M:%S')})"

        changes_backup = " (changes)" if hash_backup != hash_backup_record else " (same)"
        changes_local = " (changes)" if hash_local != hash_local_record else " (same)"

        aditional_message = ""
        if hash_backup_record is None or hash_local_record is None:
            aditional_message = "\n\n⚠️ No previous sync record exists for this game."

        message = (
            f"Changes detected in save files for:\n"
            f"<b>{game_name}</b>{aditional_message}\n\n"
            f"<b>Which file do you want to preserve?</b>\n\n"
            f"<b>1. {text_backup}</b>\n"
            f"<b>2. {text_local}</b>\n\n"
            f"Backup files (hash): {changes_backup}\n"
            f"Local files (hash): {changes_local}"
        )

        cmd = [
            'zenity',
            '--question',
            '--title=Save Game Sync',
            f'--text={message}',
            '--ok-label=Use Backup (1)',
            '--cancel-label=Use Local (2)',
            '--extra-button=Cancel',
            '--width=700',
            '--height=400' 
        ]

        result = subprocess.run(cmd, 
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True)

        if result.stderr.strip() == "Cancel":
            return "cancel"
        elif result.returncode == 0: 
            return "backup"
        else: 
            return "local"

    except Exception as e:
        logging.error(f"Error in conflict dialog: {e}")
        subprocess.run([
            'zenity',
            '--error',
            '--title=Error',
            f'--text=Error showing conflict dialog: {str(e)}'
        ], check=True)
        return "cancel"

def sync_game(game_name, game_backup_path, steamdeck_path, record, metadata):
    is_folder = metadata.get("folder_save", "").lower() != "false"
    backup_date = get_files_date(game_backup_path)
    steamdeck_date = get_files_date(steamdeck_path)
    backup_key = str(game_backup_path)
    result = False

    if not backup_date and not steamdeck_date:
        logger.info(f"No save files in {game_backup_path} or {steamdeck_path}.")
        return result

    hash_backup = compute_hash(game_backup_path) if backup_date else None
    hash_local = compute_hash(steamdeck_path) if steamdeck_date else None

    if not steamdeck_date:
        logger.info(f"Restoring backup to Steam Deck...")
        result = copy_saves(game_backup_path, steamdeck_path, is_folder)
        record.setdefault(game_name, {})[backup_key] = {
            "last_sync": datetime.now().isoformat(),
            "updated_from": "backup",
            "hash_backup": hash_backup,
            "hash_local": compute_hash(steamdeck_path),
        }
        return result

    if not backup_date:
        logger.warning(f"Warning: Local save without backup for {game_name}.")
        return False

    game_record = record.setdefault(game_name, {})
    backup_record = game_record.get(backup_key, {})

    if backup_record.get("last_sync"):
        last_sync = datetime.fromisoformat(backup_record["last_sync"])
        if (hash_backup == backup_record.get("hash_backup") and
            hash_local == backup_record.get("hash_local") and
            backup_date <= last_sync and
            steamdeck_date <= last_sync):
            logger.info(f"No changes in {game_name}.")
            return True

    action = show_sync_conflict_dialog(
        game_name, backup_date, steamdeck_date,
        hash_backup, hash_local,
        backup_record.get("hash_backup"),
        backup_record.get("hash_local")
    )

    if action == "backup":
        logger.info(f"Restoring backup...")
        result = copy_saves(game_backup_path, steamdeck_path, is_folder)
        new_local_hash = compute_hash(steamdeck_path)
    elif action == "local":
        logger.info(f"Updating backup...")
        update_backup(game_backup_path, steamdeck_path, metadata)
        new_bacup_hash = compute_hash(game_backup_path)
    else: 
        logger.info(f"Sync canceled for {game_name}.")
        return result

    game_record[backup_key] = {
        "last_sync": datetime.now().isoformat(),
        "updated_from": action,
        "hash_backup": new_bacup_hash if action == "local" else hash_backup,
        "hash_local": new_local_hash if action == "backup" else hash_local,
    }

    return result
