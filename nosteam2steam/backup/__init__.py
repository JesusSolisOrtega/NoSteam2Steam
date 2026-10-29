"""Game save backup and synchronization subsystem."""

from nosteam2steam.backup.manager import (
    main,
    run_sync,
    show_sync_options_dialog,
)
from nosteam2steam.backup.lost_saves import restore_lost_saves
from nosteam2steam.backup.creator import create_backup_gbm, create_backup_from_gbm
from nosteam2steam.backup.restore import generate_games_inventory, sync_game
from nosteam2steam.backup.archive import create_file_7z_gbm, load_metadata_from_7z, extract_archive
from nosteam2steam.backup.inventory import load_games_backup_inventory, load_sync_record, save_sync_record
from nosteam2steam.backup.conflict import show_backup_selection_dialog, show_sync_conflict_dialog

__all__ = [
    "main",
    "run_sync",
    "show_sync_options_dialog",
    "restore_lost_saves",
    "create_backup_gbm",
    "create_backup_from_gbm",
    "generate_games_inventory",
    "sync_game",
    "create_file_7z_gbm",
    "load_metadata_from_7z",
    "extract_archive",
    "load_games_backup_inventory",
    "load_sync_record",
    "save_sync_record",
    "show_backup_selection_dialog",
    "show_sync_conflict_dialog",
]
