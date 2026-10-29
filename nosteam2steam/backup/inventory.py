"""Inventory indexing and synchronization records for game save backups."""

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from nosteam2steam.config import (
    ID_MAP_PATH,
    INVENTORY_FILE,
    SYNC_RECORD_FILE,
    get_backups_directory,
)
from nosteam2steam.backup.archive import load_metadata_from_7z
from nosteam2steam.atomic import atomic_write

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
        with atomic_write(record_path, mode="w", encoding="utf-8") as file:
            json.dump(record, file, indent=4)
    except Exception as e:
        logger.info(f"Error saving sync record: {e}")


def file_needs_update(file_path, backups_path=None, days_threshold=7):
    """Checks whether the file is missing, older than backup archives, or exceeds days threshold."""
    try:
        p = Path(file_path)
        if not p.exists():
            return True
        inv_mtime = p.stat().st_mtime
        if backups_path:
            bp = Path(backups_path)
            if bp.exists():
                for sub in bp.iterdir():
                    if sub.is_dir():
                        for f in sub.glob("*.7z"):
                            if f.stat().st_mtime > inv_mtime:
                                return True
        modification_date = datetime.fromtimestamp(inv_mtime)
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


def generate_games_inventory(
    backups_path: Optional[Union[str, Path]] = None,
    inventory_path: Union[str, Path] = INVENTORY_FILE,
) -> Optional[Dict[str, Any]]:
    """
    Scans the backups directory, extracts metadata from .7z archives,
    and updates the games inventory JSON catalog with incremental caching.
    """
    inventory: Dict[str, Any] = {}
    if backups_path is None:
        backups_path = get_backups_directory()
    backups_path = Path(backups_path)
    backups_path.mkdir(parents=True, exist_ok=True)

    # Load existing inventory cache to avoid decompressing unchanged archives
    existing_cache: Dict[str, Dict[str, Any]] = {}
    if Path(inventory_path).exists():
        try:
            with open(inventory_path, "r", encoding="utf-8") as f:
                raw_inv = json.load(f)
                for g_name, entries in raw_inv.items():
                    for entry in entries:
                        f_name = entry.get("folder")
                        if f_name:
                            entry_copy = dict(entry)
                            entry_copy["game_name"] = g_name
                            existing_cache[f_name] = entry_copy
        except Exception:
            existing_cache = {}

    for folder in backups_path.iterdir():
        if not folder.is_dir():
            continue

        files_7z = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".7z"]

        if not files_7z:
            logger.warning(f"Warning: No .7z files found in {folder.name}")
            continue

        cached_folder_entry = existing_cache.get(folder.name)
        cached_files = cached_folder_entry.get("7z_files", {}) if cached_folder_entry else {}

        backups_metadata = []
        for file_7z in files_7z:
            file_stat = file_7z.stat()
            current_mtime = file_stat.st_mtime
            current_size = file_stat.st_size
            cached_file_meta = cached_files.get(file_7z.name)

            # Fast path: if archive mtime has not changed, reuse cached metadata directly
            if cached_folder_entry and cached_file_meta and "original_path" in cached_file_meta:
                try:
                    cached_dt = datetime.fromisoformat(cached_file_meta["modification_date"])
                    if abs(cached_dt.timestamp() - current_mtime) < 1.0:
                        backups_metadata.append(
                            {
                                "file": file_7z.name,
                                "metadata": {
                                    "game_name": cached_folder_entry.get("game_name", folder.name),
                                    "original_path": cached_file_meta["original_path"],
                                    "folder_save": cached_file_meta.get("folder_save", "true"),
                                    "process_name": cached_folder_entry.get("executable", ""),
                                },
                                "timestamp": current_mtime,
                                "size_bytes": cached_file_meta.get("size_bytes", current_size),
                                "has_registry": cached_file_meta.get(
                                    "has_registry",
                                    "<winreg" in str(cached_file_meta.get("original_path", "")).lower(),
                                ),
                            }
                        )
                        continue
                except (ValueError, KeyError):
                    pass

            # Slow path: decompress and read manifest XML
            metadata = load_metadata_from_7z(file_7z)
            if metadata and "game_name" in metadata and "original_path" in metadata:
                backups_metadata.append(
                    {
                        "file": file_7z.name,
                        "metadata": metadata,
                        "timestamp": current_mtime,
                        "size_bytes": current_size,
                        "has_registry": "<winreg" in str(metadata.get("original_path", "")).lower(),
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
                    "size_bytes": b.get("size_bytes", 0),
                    "has_registry": b.get("has_registry", False),
                }
                for b in backups_metadata
            },
        }

        if game_name not in inventory:
            inventory[game_name] = []

        inventory[game_name].append(game_entry)

    try:
        with atomic_write(inventory_path, mode="w", encoding="utf-8") as file:
            json.dump(inventory, file, indent=4, ensure_ascii=False)
        logger.info(f"Inventory generated and saved to {inventory_path}")
        return inventory
    except Exception as e:
        logger.error(f"Error saving inventory: {str(e)}")
        return None


def load_games_backup_inventory(inventory_path=INVENTORY_FILE):
    """
    Loads inventory from disk, automatically generating it if absent or outdated.
    """
    backups_path = Path(get_backups_directory())
    backups_path.mkdir(parents=True, exist_ok=True)
    try:
        if not Path(inventory_path).exists() or file_needs_update(inventory_path, backups_path=backups_path):
            logger.info("Inventory file does not exist or is outdated. Generating inventory...")
            if not generate_games_inventory(backups_path=backups_path, inventory_path=inventory_path):
                return None

        with open(inventory_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Error loading or generating inventory file: {e}")
        return None
