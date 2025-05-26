from backup_restore import load_games_backup_inventory, generate_games_inventory
from create_backup import load_games_mapping, verify_and_create_missing_backup

from config import DEFAULT_BACKUPS_PATH, ID_MAP_PATH, INVENTORY_FILE, STEAMDECK_PATH

def restore_game_saves(game_name, games_mapping, inventory, backups_path=DEFAULT_BACKUPS_PATH):

    current_appid = games_mapping[game_name]['app_id_short']
    alternative_appids = _get_alternative_appids(current_appid, games_mapping)

    return verify_and_create_missing_backup(game_name, games_mapping, inventory, backups_path, alternative_appids)


def _get_alternative_appids(current_appid, games_mapping):
    known_appids = {j.get('app_id_short') for j in games_mapping.values() if j.get('app_id_short')}
    unknown_folders = []
    known_folders = []

    for appid_dir in (STEAMDECK_PATH).iterdir():
        if not appid_dir.is_dir() or appid_dir.name == current_appid:
            continue
        (known_folders if appid_dir.name in known_appids else unknown_folders).append(appid_dir.name)

    return unknown_folders

def restore_lost_saves(id_map_path=ID_MAP_PATH, backups_path=DEFAULT_BACKUPS_PATH, inventory_path=INVENTORY_FILE):
    games_mapping = load_games_mapping(id_map_path)
    if not games_mapping:
        return

    inventory = load_games_backup_inventory(inventory_path)
    if not inventory:
        return

    update_inventory = False
    for game_name in games_mapping:
        if game_name not in inventory:
            update_inventory = restore_game_saves(game_name, games_mapping, inventory, backups_path) or update_inventory

    if update_inventory:
        generate_games_inventory()