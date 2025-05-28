# backup_manager.py
import subprocess
from backup_restore import (find_backups, load_games_backup_inventory, load_games_mapping,
                          load_metadata_from_7z, load_sync_record, generate_games_inventory,
                          save_sync_record, sync_game)
from create_backup import verify_and_create_missing_backup
from path_converter import transform_path_from_windows_to_proton
from restore_lost_saves import restore_lost_saves
import logging
from logging.handlers import RotatingFileHandler


from config import ID_MAP_PATH, INVENTORY_FILE, SCRIPT_DIR, get_backups_directory
from utils import select_backup_directory, with_zenity_progress

logger = logging.getLogger('GBM_Backup')

def config_logging():
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    file_handler = RotatingFileHandler(
        str(SCRIPT_DIR / "gbm_backup.log"),
        maxBytes=1*1024*1024,
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

#    console_handler = logging.StreamHandler(sys.stdout)
#    console_handler.setLevel(logging.INFO)
#    console_handler.setFormatter(logging.Formatter('%(message)s'))

    logger.addHandler(file_handler)
#    logger.addHandler(console_handler)

@with_zenity_progress("Processing", "Synchronizing saves...")
def run_sync(id_map_path=ID_MAP_PATH, backups_path=get_backups_directory(), inventory_path=INVENTORY_FILE):
    config_logging()

    logger.info("Starting synchronization process")

    games_mapping = load_games_mapping(id_map_path)

    if not games_mapping:
        logger.error("Could not load the game mapping file")
        return

    inventory = load_games_backup_inventory(inventory_path)
    if not inventory:
        logger.error("Could not load or generate the inventory file")
        return

    record = load_sync_record()

    inventory_update = False

    for game_name, game_data in games_mapping.items():
        logger.info(f"► Processing {game_name}")
        if game_name not in inventory:
            if verify_and_create_missing_backup(game_name, games_mapping, inventory, record):
                inventory_update = True
                logger.info(f"✓ New backup created for {game_name}")
                continue

        game_id = game_data.get("app_id_short")
        if not game_id:
            logger.warning(f"Game {game_name} without short ID")
            continue

        backups_paths = find_backups(game_name, inventory, record, backups_path)

        if not backups_paths:
            logger.warning(f"No backup found for {game_name}")
            continue

        for file_path_7z in backups_paths:
            metadata = load_metadata_from_7z(file_path_7z)
            if not metadata:
                logger.error(f"Error loading metadata for {file_path_7z}")
                continue

            steamdeck_path = transform_path_from_windows_to_proton(metadata["original_path"], game_data)

            if sync_game(game_name, file_path_7z, steamdeck_path, record, metadata):
                logger.info(f"✓ {game_name} synchronized successfully from {file_path_7z.name}")
            else:
                logger.error(f"✗ Problem synchronizing {game_name} from {file_path_7z.name}")

    if inventory_update:
        inventory = generate_games_inventory()
        logger.debug("Inventory updated")
    save_sync_record(record)
    logger.info("Synchronization process completed")


def show_sync_options_dialog():
    try:
        script = """
        #!/bin/bash
        selection=$(zenity --list \
                                 --title="Save Manager" \
                                 --text="Select an option:" \
                                 --column="Option" \
                                 --hide-header \
                                 --width=450 \
                                 --height=300 \
                                 "Synchronize Saves" \
                                 "Restore Lost Saves" \
                                 "Select backups folder" \
                                 "Exit")

        case "$selection" in
            "Synchronize Saves") echo "0" ;;
            "Restore Lost Saves") echo "1" ;;
            "Select backups folder") echo "2" ;;
            *) echo "3" ;;
        esac
        """

        result = subprocess.run(['bash', '-c', script],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 text=True)

        option = result.stdout.strip()

        if option == '0':
            run_sync()
        elif option == '1':
            restore_lost_saves()
        elif option == '2':
            select_backup_directory()


    except Exception as e:
        logger.error(f"Error in options dialog: {e}")
        subprocess.run(['zenity', '--error',
                          '--title=Error',
                          f'--text=Error displaying options: {str(e)}'],
                         check=True)

def main():
    show_sync_options_dialog()

if __name__ == "__main__":
    show_sync_options_dialog()
