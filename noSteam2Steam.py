# no_steam_2_steam.py
import logging
import subprocess
import sys

from backup_manager import run_sync
from utils import manage_sync_folders, show_cleanup_dialog, manage_syncthingy_service

from config import GAME_DATA_MANAGER, ADD2STEAM, BACKUP_MANAGER, MANUAL_ADD_SCRIPT

logger = logging.getLogger("no_steam_to_steam.log")

def show_main_menu():
    menu = [
        "1", "Automatic sync (add games and sync saves)",
        "2", "Add games to Steam automatically",
        "3", "Game saves synchronization",
        "4", "Manually add a game to Steam",
        "5", "Clean NoSteam2Steam configuration",
        "6", "Enable/disable Syncthing",
        "7", "Change synchronized game folders",
        "8", "Exit"
    ]
    
    cmd = [
        'zenity', '--list',
        '--title=NoSteam2Steam - Non-Steam Games Management',
        '--text=Select an option:',
        '--column=Option', '--column=Description',
        '--width=650', '--height=400',
    ] + menu

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def run_script(script_path, args=None):
    if not script_path.exists():
        logger.error(f"Error: Script not found {script_path}")
        return False
    
    try:
        if script_path.suffix == '.py':
            cmd = ['python3', str(script_path)]
        else:
            cmd = ['bash', str(script_path)]
        
        if args:
            cmd.extend(args)
        
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error executing {script_path}: {e}")
        return False

def main():
    while True:
        option = show_main_menu()
        
        if not option or option == "8":
            break
            
        if option == "1":
            if not run_script(GAME_DATA_MANAGER):
                continue
            if not run_script(ADD2STEAM):
                continue
            try:
                run_sync()
            except Exception as e:
                logger.error(f"Sync error: {e}")
                continue
            
        elif option == "2":
            if not run_script(GAME_DATA_MANAGER):
                continue
            run_script(ADD2STEAM)
            
        elif option == "3":
            run_script(BACKUP_MANAGER)
            
        elif option == "4":
            run_script(MANUAL_ADD_SCRIPT)
        
        elif option == "5":
            try:
                show_cleanup_dialog()
            except Exception as e:
                logger.error(f"Error cleaning configuration: {e}")
                continue
        elif option == "6":
            try:
                manage_syncthingy_service()
            except Exception as e:
                logger.error(f"Error: {e}")
                continue
            
        elif option == "7":
            try:
                manage_sync_folders()
            except Exception as e:
                logger.error(f"Error: {e}")
                continue
            
        subprocess.run([
            'zenity', '--info',
            '--title=Operation completed',
            '--text=The selected action has finished.',
            '--timeout=2'
        ])

if __name__ == "__main__":
    try:
        subprocess.run(['zenity', '--version'], check=True, stdout=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("Error: Zenity is not installed. Please install it with:")
        logger.error("sudo apt install zenity")
        sys.exit(1)
    
    main()
