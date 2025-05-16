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


from config import ID_MAP_PATH, get_backups_directory
from utils import select_backup_directory

logger = logging.getLogger('GBM_Backup')

def config_logging():
    if logger.hasHandlers():
        logger.handlers.clear()
    
    logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    file_handler = RotatingFileHandler(
        'gbm_backup.log',
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

def run_sync(id_map_path=ID_MAP_PATH, backups_path=get_backups_directory(), inventory_path="games_backups_inventory.json"):
    config_logging() 
    
    logger.info("Iniciando proceso de sincronización")

    games_mapping = load_games_mapping(id_map_path)

    if not games_mapping:
        logger.error("No se pudo cargar el archivo de mapeo de juegos")
        return

    inventory = load_games_backup_inventory(inventory_path)
    if not inventory:
        logger.error("No se pudo cargar o generar el archivo de inventario")
        return

    record = load_sync_record()

    inventory_update = False

    for game_name, game_data in games_mapping.items():
        logger.info(f"► Procesando {game_name}")
        if game_name not in inventory:
            if verify_and_create_missing_backup(game_name, games_mapping, inventory, record):
                inventory_update = True
                logger.info(f"✓ Nuevo backup creado para {game_name}")
                continue

        game_id = game_data.get("app_id_short")
        if not game_id:
            logger.warning(f"Juego {game_name} sin ID corto")
            continue

        backups_paths = find_backups(game_name, inventory, record, backups_path)
        
        if not backups_paths:
            logger.warning(f"No se encontró backup para {game_name}")
            continue

        for file_path_7z in backups_paths:
            metadata = load_metadata_from_7z(file_path_7z)
            if not metadata:
                logger.error(f"Error cargando metadatos para {file_path_7z}")
                continue

            steamdeck_path = transform_path_from_windows_to_proton(metadata["original_path"], game_data)

            if sync_game(game_name, file_path_7z, steamdeck_path, record, metadata):
                logger.info(f"✓ {game_name} sincronizado correctamente desde {file_path_7z.name}")
            else:
                logger.error(f"✗ Problema sincronizando {game_name} desde {file_path_7z.name}")

    if inventory_update:
        inventory = generate_games_inventory()
        logger.debug("Inventario actualizado")
    save_sync_record(record)
    logger.info("Proceso de sincronización completado")


def show_sync_options_dialog():
    try:
        script = """
        #!/bin/bash
        selection=$(zenity --list \
                    --title="Gestor de Saves" \
                    --text="Selecciona una opción:" \
                    --column="Opción" \
                    --hide-header \
                    --width=450 \
                    --height=300 \
                    "Sincronizar Saves" \
                    "Restaurar Saves Perdidos" \
                    "Seleccionar carpeta de backups" \
                    "Salir")
        
        case "$selection" in
            "Sincronizar Saves") echo "0" ;;
            "Restaurar Saves Perdidos") echo "1" ;;
            "Seleccionar carpeta de backups") echo "2" ;;
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
        logger.error(f"Error en diálogo de opciones: {e}")
        subprocess.run(['zenity', '--error',
                      '--title=Error',
                      f'--text=Error al mostrar opciones: {str(e)}'],
                      check=True)

if __name__ == "__main__":
    show_sync_options_dialog()
