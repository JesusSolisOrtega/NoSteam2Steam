# backup_manager.py
import logging
from logging.handlers import RotatingFileHandler

from nosteam2steam.backup.restore import (
    find_backups,
    load_games_backup_inventory,
    load_games_mapping,
    load_metadata_from_7z,
    load_sync_record,
    generate_games_inventory,
    save_sync_record,
    sync_game,
)
from nosteam2steam.backup.creator import load_gbm_configs, verify_and_create_missing_backup
from nosteam2steam.backup.path_converter import transform_path_from_windows_to_proton
from nosteam2steam.backup.lost_saves import restore_lost_saves

from nosteam2steam.config import ID_MAP_PATH, INVENTORY_FILE, SCRIPT_DIR, get_backups_directory
from nosteam2steam.utils import select_backup_directory
from nosteam2steam import ui

logger = logging.getLogger(__name__)


def config_logging():
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler = RotatingFileHandler(
        str(SCRIPT_DIR / "gbm_backup.log"), maxBytes=1 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    #    console_handler = logging.StreamHandler(sys.stdout)
    #    console_handler.setLevel(logging.INFO)
    #    console_handler.setFormatter(logging.Formatter('%(message)s'))

    logger.addHandler(file_handler)


#    logger.addHandler(console_handler)


def run_sync(id_map_path=ID_MAP_PATH, backups_path=None, inventory_path=INVENTORY_FILE):
    config_logging()
    if backups_path is None:
        backups_path = get_backups_directory()

    logger.info("Starting synchronization process")

    games_mapping = load_games_mapping(id_map_path)

    if not games_mapping:
        logger.error("Could not load the game mapping file")
        return {"synced": 0, "created": 0, "total": 0}

    with ui.progress_dialog("NoSteam2Steam", "Iniciando sincronización de partidas guardadas...") as progress:
        inventory = load_games_backup_inventory(inventory_path)
        if not inventory:
            logger.error("Could not load or generate the inventory file")
            return {"synced": 0, "created": 0, "total": 0}

        record = load_sync_record()

        inventory_update = False
        gbm_configs = None
        synced_count = 0
        created_count = 0

        total_games = len(games_mapping)
        for idx, (game_name, game_data) in enumerate(games_mapping.items(), 1):
            progress.update(f"Sincronizando partidas ({idx}/{total_games}): {game_name}")
            logger.info(f"► Processing {game_name}")
            if game_name not in inventory:
                if gbm_configs is None:
                    gbm_configs = load_gbm_configs(SCRIPT_DIR / "GBM_Official.xml")
                if verify_and_create_missing_backup(
                    game_name, games_mapping, inventory, record, gbm_configs=gbm_configs
                ):
                    inventory_update = True
                    created_count += 1
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
                metadata = None
                for entry in inventory.get(game_name, []):
                    file_meta = entry.get("7z_files", {}).get(file_path_7z.name)
                    if file_meta and "original_path" in file_meta and "folder_save" in file_meta:
                        metadata = {
                            "game_name": game_name,
                            "original_path": file_meta["original_path"],
                            "folder_save": file_meta["folder_save"],
                            "process_name": entry.get("executable", ""),
                        }
                        break

                if not metadata:
                    metadata = load_metadata_from_7z(file_path_7z)

                if not metadata:
                    logger.error(f"Error loading metadata for {file_path_7z}")
                    continue

                steamdeck_path = transform_path_from_windows_to_proton(metadata["original_path"], game_data)

                if sync_game(game_name, file_path_7z, steamdeck_path, record, metadata):
                    synced_count += 1
                    logger.info(f"✓ {game_name} synchronized successfully from {file_path_7z.name}")
                else:
                    logger.error(f"✗ Problem synchronizing {game_name} from {file_path_7z.name}")

        if inventory_update:
            inventory = generate_games_inventory()
            logger.debug("Inventory updated")
        save_sync_record(record)
        logger.info("Synchronization process completed")
        return {"synced": synced_count, "created": created_count, "total": total_games}


def show_sync_options_dialog():
    try:
        menu_items = [
            ("1", "Synchronize Saves"),
            ("2", "Restore Lost Saves"),
            ("3", "Select backups folder"),
            ("4", "Exit"),
        ]

        option = ui.show_menu(
            title="Save Manager", text="Select an option:", menu_items=menu_items, width=450, height=300
        )

        if option == "1":
            run_sync()
        elif option == "2":
            restore_lost_saves()
        elif option == "3":
            select_backup_directory()

    except Exception as e:
        logger.error(f"Error in options dialog: {e}")
        ui.show_error("Error", f"Error displaying options: {str(e)}")


def main():
    show_sync_options_dialog()


if __name__ == "__main__":
    show_sync_options_dialog()
