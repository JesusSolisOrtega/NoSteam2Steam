"""Interactive configuration wizards and user maintenance dialogs."""

import logging
import os
from pathlib import Path
from typing import List

from nosteam2steam import ui
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
        file_path = os.path.join(script_dir, file)
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
            ("1", "Delete all configuration"),
            ("2", "Delete configuration and images"),
            ("3", "Delete detected games configuration (does not delete games)"),
            ("4", "Delete save games configuration (does not delete saves)"),
            ("5", "Delete game images"),
        ]
        selection = ui.show_menu(
            title="Cleanup Options",
            text="Select what to delete:",
            menu_items=cleanup_options,
            width=500,
            height=350,
        )

        if not selection:
            return False

        if not ui.ask_question(
            title="Confirm",
            text="Are you sure you want to continue? This action cannot be undone.",
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
            ui.show_info(title="Completed", text="Cleanup completed successfully", width=200)
        else:
            ui.show_error(title="Error", text="Errors occurred during cleanup", width=200)

        return success

    except Exception as e:
        ui.show_error(title="Error", text=f"Unexpected error: {e}", width=300)
        return False


def manage_sync_folders() -> List[str]:
    """Manages custom synchronization folders via Zenity file pickers and checklists."""
    current_folders = []
    if os.path.exists(SYNC_FOLDERS_FILE):
        with open(SYNC_FOLDERS_FILE, "r", encoding="utf-8") as f:
            current_folders = [line.strip() for line in f if line.strip()]

    while True:
        choice = ui.show_menu(
            title="Sync Folders Management",
            text="Select an action:",
            menu_items=[("Add folder", ""), ("Remove folder", "")],
            hide_header=True,
            cancel_label="Exit",
            width=350,
            height=200,
        )

        if not choice:
            break

        if choice == "Add folder":
            new_folder = ui.select_path(title="Select folder to sync", directory=True)
            if new_folder and new_folder not in current_folders:
                current_folders.append(new_folder)
                with open(SYNC_FOLDERS_FILE, "w", encoding="utf-8") as f:
                    f.write("\n".join(current_folders))

        elif choice == "Remove folder":
            if not current_folders:
                ui.show_info(title="Info", text="No folders to remove", timeout=2)
                continue

            selected = ui.show_checklist(
                title="Select folders to remove",
                text="Check folders to remove:",
                items=[(f, False) for f in current_folders],
                column_name="Folder",
            )

            if selected:
                current_folders = [f for f in current_folders if f not in selected]
                with open(SYNC_FOLDERS_FILE, "w", encoding="utf-8") as f:
                    f.write("\n".join(current_folders))

    return current_folders


def select_backup_directory() -> None:
    """Prompts user to select or reset the backup repository location."""
    backup_logger = logging.getLogger(__name__)
    config_file = ALTERNATIVE_BACKUPS_PATH_FILE
    default_dir_str = f"Use default directory ({DEFAULT_BACKUPS_PATH})"

    option = ui.show_menu(
        title="Backup Directory Selection",
        text="Select an option:",
        menu_items=[("Select custom directory", ""), (default_dir_str, "")],
        width=400,
        height=200,
    )

    if not option:
        backup_logger.info("Operation cancelled by user")
        return

    if option == "Select custom directory":
        selected_dir = ui.select_path(title="Select backup directory", directory=True)
        if selected_dir:
            with open(config_file, "w", encoding="utf-8") as f:
                f.write(selected_dir)
            backup_logger.info(f"Selected directory saved: {selected_dir}")
        else:
            backup_logger.info("Operation cancelled by user")

    elif option == default_dir_str:
        if os.path.exists(config_file):
            os.remove(config_file)
            backup_logger.info("Restored default directory")
        else:
            backup_logger.info("Already using default directory")
