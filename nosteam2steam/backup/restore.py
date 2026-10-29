"""Game save restoration and synchronization orchestrator."""

from datetime import datetime
import logging
from pathlib import Path

from nosteam2steam.config import DEFAULT_BACKUPS_PATH
from nosteam2steam.utils import compute_hash
from nosteam2steam.backup.archive import (
    copy_saves,
    extract_archive,
    load_metadata_from_7z,
    update_archive,
    update_backup,
)
from nosteam2steam.backup.inventory import (
    file_needs_update,
    generate_games_inventory,
    get_files_date,
    load_games_backup_inventory,
    load_games_mapping,
    load_sync_record,
    save_sync_record,
)
from nosteam2steam.backup.conflict import (
    show_backup_selection_dialog,
    show_sync_conflict_dialog,
)

logger = logging.getLogger(__name__)


def find_backups(game_name, inventory, record, backups_path=DEFAULT_BACKUPS_PATH):
    """
    Locates available .7z backups for a game from inventory, resolving duplicates
    either automatically via synchronization record or via user dialog.
    """
    if game_name not in inventory:
        logger.info(f"No backups found for {game_name} in inventory.")
        return None

    all_backups = []
    backups_path = Path(backups_path)

    for entry in inventory[game_name]:
        folder = entry["folder"]
        folder_path = backups_path / folder

        if not folder_path.exists():
            logger.warning(f"Warning: Folder {folder} does not exist.")
            continue

        for file, metadata in entry["7z_files"].items():
            file_path = folder_path / file
            if file_path.exists():
                all_backups.append(
                    {
                        "file": file_path,
                        "str_path": str(file_path),
                        "folder": folder,
                        "original_path": metadata["original_path"],
                        "modification_date": metadata["modification_date"],
                        "timestamp": datetime.fromisoformat(metadata["modification_date"]).timestamp(),
                    }
                )

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

        record_backups = [b for b in backups if game_name in record and str(b["str_path"]) in record[game_name]]

        if record_backups:
            recorded_backups_sorted = sorted(
                record_backups,
                key=lambda x: x["timestamp"],
                reverse=True,
            )
            chosen_backups.append(recorded_backups_sorted[0]["file"])
            logger.info(f"Automatic selection: {recorded_backups_sorted[0]['file'].name} (already registered)")
            continue

        backups_sorted = sorted(backups, key=lambda x: x["timestamp"], reverse=True)
        for i, backup in enumerate(backups_sorted):
            backup["most_recent"] = i == 0

        selected_idx = show_backup_selection_dialog(backups_sorted)
        if selected_idx == -1:
            return None

        chosen_backups.append(backups_sorted[selected_idx]["file"])

    return chosen_backups


def sync_game(game_name, game_backup_path, steamdeck_path, record, metadata):
    """
    Synchronizes save data between local Proton prefix and backup repository,
    detecting hash/timestamp modifications and requesting user guidance upon conflict.
    """
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
        logger.info("Restoring backup to Steam Deck...")
        result = extract_archive(game_backup_path, steamdeck_path, is_folder)
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
        if (
            hash_backup == backup_record.get("hash_backup")
            and hash_local == backup_record.get("hash_local")
            and backup_date <= last_sync
            and steamdeck_date <= last_sync
        ):
            logger.info(f"No changes in {game_name}.")
            return True

    action = show_sync_conflict_dialog(
        game_name,
        backup_date,
        steamdeck_date,
        hash_backup,
        hash_local,
        backup_record.get("hash_backup"),
        backup_record.get("hash_local"),
    )

    if action == "backup":
        logger.info("Restoring backup...")
        result = extract_archive(game_backup_path, steamdeck_path, is_folder)
        new_local_hash = compute_hash(steamdeck_path)
        new_backup_hash = hash_backup
    elif action == "local":
        logger.info("Updating backup...")
        update_archive(game_backup_path, steamdeck_path, metadata)
        new_backup_hash = compute_hash(game_backup_path)
        new_local_hash = hash_local
    else:
        logger.info(f"Sync canceled for {game_name}.")
        return result

    game_record[backup_key] = {
        "last_sync": datetime.now().isoformat(),
        "updated_from": action,
        "hash_backup": new_backup_hash,
        "hash_local": new_local_hash,
    }

    return result


__all__ = [
    "find_backups",
    "sync_game",
    "copy_saves",
    "extract_archive",
    "update_backup",
    "update_archive",
    "load_metadata_from_7z",
    "generate_games_inventory",
    "load_games_backup_inventory",
    "file_needs_update",
    "load_sync_record",
    "save_sync_record",
    "load_games_mapping",
    "get_files_date",
    "show_backup_selection_dialog",
    "show_sync_conflict_dialog",
]
