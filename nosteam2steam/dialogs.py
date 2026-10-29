"""Interactive configuration wizards and user maintenance dialogs."""

import logging
import os
from pathlib import Path
from typing import List

from nosteam2steam import ui
from nosteam2steam.i18n import _
from nosteam2steam.atomic import atomic_write
from nosteam2steam.config import (
    ALTERNATIVE_BACKUPS_PATH_FILE,
    DEFAULT_BACKUPS_PATH,
    SCRIPT_DIR,
    STEAM_USERDATA_DIR,
    SYNC_FOLDERS_FILE,
)
from nosteam2steam.steam.environment import get_current_user

logger = logging.getLogger(__name__)


def delete_current_config(game_data=True, saves=True) -> bool:
    """Removes generated JSON and TXT configuration files from disk."""
    config_files = []
    if game_data:
        config_files.append("games.json")
        config_files.append("steam_id_mapping.json")
        config_files.append("user_mapping.json")
        config_files.append("sync_folders.txt")
    if saves:
        config_files.append("games_backups_inventory.json")
        config_files.append("sync_record.json")
        config_files.append("alternative_backups_path.txt")

    success = True
    script_dir = SCRIPT_DIR

    for file in config_files:
        for candidate in (file, f"{file}.bak"):
            file_path = os.path.join(script_dir, candidate)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Deleted: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting {file_path}: {e}")
                success = False

    return success


def delete_games_images() -> bool:
    """Deletes cached grid artwork and icons from Steam userdata config."""
    user = get_current_user()
    if not user:
        logger.info("Could not determine current user")
        return False

    steam_config_path = Path(STEAM_USERDATA_DIR) / user / "config"
    folders_to_clear = ["grid", "icons"]

    success = True
    for folder in folders_to_clear:
        folder_path = steam_config_path / folder
        try:
            if folder_path.exists():
                for item in folder_path.iterdir():
                    if item.is_file():
                        item.unlink()
        except Exception as e:
            logger.error(f"Error cleaning {folder_path}: {e}")
            success = False

    return success


def show_cleanup_dialog() -> bool:
    """Presents user with a Zenity menu to selectively clear caches and configurations."""
    try:
        cleanup_options = [
            ("1", _("Delete all configuration")),
            ("2", _("Delete configuration and images")),
            ("3", _("Delete detected games configuration (does not delete games)")),
            ("4", _("Delete save games configuration (does not delete saves)")),
            ("5", _("Delete game images")),
        ]
        selection = ui.show_menu(
            title=_("Cleanup Options"),
            text=_("Select items to delete:"),
            menu_items=cleanup_options,
            width=500,
            height=350,
        )

        if not selection:
            return False

        if not ui.ask_question(
            title=_("Confirm Action"),
            text=_("Are you sure you want to proceed? This operation cannot be undone."),
            width=300,
        ):
            return False

        success = False
        if selection == "1":
            success = delete_current_config(game_data=True, saves=True)
        elif selection == "2":
            delete_current_config(game_data=True, saves=True)
            success = delete_games_images()
        elif selection == "3":
            success = delete_current_config(game_data=True, saves=False)
        elif selection == "4":
            success = delete_current_config(game_data=False, saves=True)
        elif selection == "5":
            success = delete_games_images()

        if success:
            ui.show_info(title=_("Completed"), text=_("Cleanup completed successfully."), width=250)
        else:
            ui.show_error(title=_("Error"), text=_("Errors occurred during cleanup."), width=250)

        return success

    except Exception as e:
        ui.show_error(title=_("Error"), text=_("An unexpected error occurred: {error}", error=str(e)), width=300)
        return False


def manage_sync_folders() -> List[str]:
    """Manages custom synchronization folders via Zenity file pickers and checklists."""
    current_folders = []
    if os.path.exists(SYNC_FOLDERS_FILE):
        with open(SYNC_FOLDERS_FILE, "r", encoding="utf-8") as f:
            current_folders = [line.strip() for line in f if line.strip()]

    add_label = _("Add folder")
    remove_label = _("Remove folder")

    while True:
        choice = ui.show_menu(
            title=_("Sync Folders Management"),
            text=_("Select an action:"),
            menu_items=[(add_label, ""), (remove_label, "")],
            hide_header=True,
            cancel_label=_("Exit"),
            width=350,
            height=200,
        )

        if not choice:
            break

        if choice in (add_label, "Add folder"):
            new_folder = ui.select_path(title=_("Select folder to sync"), directory=True)
            if new_folder and new_folder not in current_folders:
                current_folders.append(new_folder)
                with atomic_write(SYNC_FOLDERS_FILE, mode="w", encoding="utf-8") as out_f:
                    out_f.write("\n".join(current_folders))

        elif choice in (remove_label, "Remove folder"):
            if not current_folders:
                ui.show_info(title=_("Info"), text=_("No folders to remove"), timeout=2)
                continue

            selected = ui.show_checklist(
                title=_("Select folders to remove"),
                text=_("Check folders to remove:"),
                items=[(folder_item, False) for folder_item in current_folders],
                column_name=_("Folder"),
            )

            if selected:
                current_folders = [folder_item for folder_item in current_folders if folder_item not in selected]
                with atomic_write(SYNC_FOLDERS_FILE, mode="w", encoding="utf-8") as out_f:
                    out_f.write("\n".join(current_folders))

    return current_folders


def select_backup_directory() -> None:
    """Prompts user to select or reset the backup repository location."""
    backup_logger = logging.getLogger(__name__)
    config_file = ALTERNATIVE_BACKUPS_PATH_FILE
    default_dir_str = _("Use default directory ({path})", path=str(DEFAULT_BACKUPS_PATH))
    custom_dir_str = _("Select custom directory")

    option = ui.show_menu(
        title=_("Backup Directory Selection"),
        text=_("Select an option:"),
        menu_items=[(custom_dir_str, ""), (default_dir_str, "")],
        width=450,
        height=200,
    )

    if not option:
        backup_logger.info("Operation cancelled by user")
        return

    if option in (custom_dir_str, "Select custom directory"):
        selected_dir = ui.select_path(title=_("Select backup directory"), directory=True)
        if selected_dir:
            with atomic_write(config_file, mode="w", encoding="utf-8") as f:
                f.write(selected_dir)
            backup_logger.info(f"Selected directory saved: {selected_dir}")
        else:
            backup_logger.info("Operation cancelled by user")

    elif option == default_dir_str or option.startswith("Use default directory"):
        if os.path.exists(config_file):
            os.remove(config_file)
            backup_logger.info("Restored default directory")
        else:
            backup_logger.info("Already using default directory")
