"""Inventory indexing and synchronization records for game save backups."""

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, Union

from nosteam2steam.config import (
    ID_MAP_PATH,
    INVENTORY_FILE,
    SYNC_RECORD_FILE,
    get_backups_directory,
)
from nosteam2steam.backup.archive import load_metadata_from_7z

logger = logging.getLogger(__name__)


def load_games_mapping(path_id_map=ID_MAP_PATH):
    """Loads game ID mapping dictionary from JSON configuration file."""
    try:
        with open(path_id_map, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Error loading JSON file: {e}")
        return None


def load_sync_record(record_path: Union[str, Path] = SYNC_RECORD_FILE) -> Dict[str, Any]:
    """Loads synchronization audit record from JSON file."""
    try:
        p = Path(record_path)
        if p.exists():
            with open(p, "r", encoding="utf-8") as file:
                return json.load(file)
        return {}
    except Exception as e:
        logger.info(f"Error loading sync record: {e}")
        return {}


def save_sync_record(record: Dict[str, Any], record_path: Union[str, Path] = SYNC_RECORD_FILE) -> None:
    """Persists synchronization audit record to JSON file."""
    try:
        with open(record_path, "w", encoding="utf-8") as file:
            json.dump(record, file, indent=4)
    except Exception as e:
        logger.info(f"Error saving sync record: {e}")


def file_needs_update(file_path, days_threshold=7):
    """Checks whether the file modification age exceeds the specified threshold."""
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


def get_files_date(path):
    """Returns the most recent modification timestamp of a file or directory tree."""
    path = Path(path)
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


def generate_games_inventory(backups_path=None, inventory_path=INVENTORY_FILE):
    """
    Scans the backups directory, extracts metadata from .7z archives,
    and updates the games inventory JSON catalog.
    """
    inventory = {}
    if backups_path is None:
        backups_path = get_backups_directory()
    backups_path = Path(backups_path)
    backups_path.mkdir(parents=True, exist_ok=True)

    for folder in backups_path.iterdir():
        if not folder.is_dir():
            continue

        files_7z = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".7z"]

        if not files_7z:
            logger.warning(f"Warning: No .7z files found in {folder.name}")
            continue

        backups_metadata = []
        for file_7z in files_7z:
            metadata = load_metadata_from_7z(file_7z)
            if metadata and "game_name" in metadata and "original_path" in metadata:
                backups_metadata.append(
                    {
                        "file": file_7z.name,
                        "metadata": metadata,
                        "timestamp": file_7z.stat().st_mtime,
                    }
                )

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
                    "folder_save": b["metadata"].get("folder_save", "true"),
                    "modification_date": datetime.fromtimestamp(b["timestamp"]).isoformat(),
                }
                for b in backups_metadata
            },
        }

        if game_name not in inventory:
            inventory[game_name] = []

        inventory[game_name].append(game_entry)

    try:
        with open(inventory_path, "w", encoding="utf-8") as file:
            json.dump(inventory, file, indent=4, ensure_ascii=False)
        logger.info(f"Inventory generated and saved to {inventory_path}")
        return inventory
    except Exception as e:
        logger.error(f"Error saving inventory: {str(e)}")
        return False


def load_games_backup_inventory(inventory_path=INVENTORY_FILE):
    """
    Loads inventory from disk, automatically generating it if absent or outdated.
    """
    backups_path = Path(get_backups_directory())
    backups_path.mkdir(parents=True, exist_ok=True)
    try:
        if not Path(inventory_path).exists() or file_needs_update(inventory_path):
            logger.info("Inventory file does not exist or is outdated. Generating inventory...")
            if not generate_games_inventory(backups_path=backups_path, inventory_path=inventory_path):
                return None

        with open(inventory_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Error loading or generating inventory file: {e}")
        return None
