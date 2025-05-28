from functools import wraps
import hashlib
import logging
import os
from pathlib import Path
from typing import List
from config import get_current_user
import subprocess
from concurrent.futures import ThreadPoolExecutor

from config import ALTERNATIVE_BACKUPS_PATH_FILE, SCRIPT_DIR, SERVICE_FILE, SYNC_FOLDERS_FILE

logger = logging.getLogger("no_steam_to_steam.log")

def compute_hash(path, max_workers=None, size_threshold=100*1024*1024):
    path = Path(path)

    try:
        if path.is_file():
            return _hash_file(path, size_threshold)
        elif path.is_dir():
            return _hash_dir(path, max_workers, size_threshold)
    except Exception as e:
        logger.error(f"Error calculating hash: {path} - {str(e)}")
        return None

def _hash_file(file_path, size_threshold, sample_size=1*1024*1024):
    hasher = hashlib.blake2b(digest_size=32)
    
    try:
        stat = file_path.stat()
        file_size = stat.st_size
        mtime = stat.st_mtime_ns

        with open(file_path, 'rb') as f:
            if file_size <= size_threshold:
                for block in iter(lambda: f.read(128*1024), b''):
                    hasher.update(block)
            else:
                hasher.update(f.read(sample_size))
                
                num_blocks = 4
                step = max((file_size - sample_size) // num_blocks, sample_size)
                
                for i in range(1, num_blocks + 1):
                    f.seek(i * step)
                    hasher.update(f.read(sample_size))
                
                hasher.update(str(file_size).encode())
                hasher.update(str(mtime).encode())

        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}")
        return None

def _hash_dir(dir_path, max_workers=None, size_threshold=150*1024*1024):
    hasher = hashlib.blake2b(digest_size=32)
    files = []

    for root, _, filenames in os.walk(dir_path):
        for fname in filenames:
            full_path = Path(root) / fname
            try:
                stat = full_path.stat()
                files.append((full_path, stat.st_size, stat.st_mtime_ns))
            except Exception:
                continue

    files.sort(key=lambda x: str(x[0]))

    def process_file(file_item):
        file_path, file_size, mtime = file_item
        file_hasher = hashlib.blake2b(digest_size=32)
        
        try:
            with open(file_path, 'rb') as f:
                if file_size <= size_threshold:
                    for block in iter(lambda: f.read(128*1024), b''):
                        file_hasher.update(block)
                else:
                    sample_size = 1 * 1024 * 1024
                    file_hasher.update(f.read(sample_size))
                    f.seek(file_size // 3)
                    file_hasher.update(f.read(sample_size))
                    f.seek(2 * file_size // 3)
                    file_hasher.update(f.read(sample_size))
                    try:
                        f.seek(-sample_size, 2)
                        file_hasher.update(f.read())
                    except OSError:
                        pass 

                    file_hasher.update(str(file_size).encode())
                    file_hasher.update(str(mtime).encode())

            return file_hasher.digest()
        except Exception:
            return b'\x00' * 32

    with ThreadPoolExecutor(max_workers=max_workers or os.cpu_count()) as executor:
        for file_hash in executor.map(process_file, files):
            hasher.update(file_hash)

    return hasher.hexdigest()

def delete_current_config(game_data=True, saves=True) -> bool:
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
    user = get_current_user()
    if not user:
        logger.info("Could not determine current user")
        return False
    
    steam_config_path = Path(f"/home/deck/.steam/steam/userdata/{user}/config")
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

def show_cleanup_dialog():
    try:
        selection = subprocess.run([
            'zenity',
            '--list',
            '--title=Cleanup Options',
            '--text=Select what to delete:',
            '--column=Option', '--column=Description',
            '1', 'Delete all configuration',
            '2', 'Delete configuration and images',
            '3', 'Delete detected games configuration (does not delete games)',
            '4', 'Delete save games configuration (does not delete saves)',
            '5', 'Delete game images',
            '--height=350',
            '--width=500'
        ], capture_output=True, text=True).stdout.strip()
        
        if not selection:
            return False

        confirm = subprocess.run([
            'zenity',
            '--question',
            '--title=Confirm',
            '--text=Are you sure you want to continue? This action cannot be undone.',
            '--width=300'
        ]).returncode

        if confirm != 0:
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
            subprocess.run([
                'zenity',
                '--info',
                '--title=Completed',
                '--text=Cleanup completed successfully',
                '--width=200'
            ])
        else:
            subprocess.run([
                'zenity',
                '--error',
                '--title=Error',
                '--text=Errors occurred during cleanup',
                '--width=200'
            ])

        return success

    except Exception as e:
        subprocess.run([
            'zenity',
            '--error',
            '--title=Error',
            '--text=Unexpected error: ' + str(e),
            '--width=300'
        ])
        return False

def manage_syncthingy_service():
    def is_active():
        return subprocess.run(["systemctl", "--user", "is-active", "syncthingy.service"], 
                            capture_output=True).returncode == 0
    
    def is_enabled():
        return subprocess.run(["systemctl", "--user", "is-enabled", "syncthingy.service"],
                            capture_output=True).returncode == 0
    
    def show_dialog():
        active = is_active()
        zenity_cmd = [
            "zenity", "--list", "--radiolist",
            "--title=SyncThingy Control",
            f"--text=Status: {'ACTIVE' if active else 'INACTIVE'}\nRestart required for full changes",
            "--column=Selection", "--column=Action",
            "TRUE", f"{'Deactivate' if active else 'Activate'} SyncThingy",
            "FALSE", "Exit",
            "--width=350", "--height=250"
        ]
        result = subprocess.run(zenity_cmd, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    
    if not SERVICE_FILE.exists():
        install = subprocess.run([
            "zenity", "--question",
            "--text=Service not installed. Install SyncThingy in background?",
            "--ok-label=Install", "--cancel-label=Cancel"
        ]).returncode == 0
        
        if install:
            SERVICE_FILE.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([
                "wget", "-qO", str(SERVICE_FILE),
                "https://raw.githubusercontent.com/zocker-160/SyncThingy/master/linux_packaging/syncthingy.service"
            ], check=True)
            subprocess.run(["systemctl", "--user", "daemon-reload"])
            subprocess.run([
                "zenity", "--info",
                "--text=Service installed. Run again to control.",
                "--timeout=2"
            ])
        return False
    
    choice = show_dialog()
    if not choice or "Exit" in choice:
        return False
    
    if "Activate" in choice or "Deactivate" in choice:
        active = is_active()
        try:
            if active:
                subprocess.run(["systemctl", "--user", "stop", "syncthingy.service"], check=True)
                subprocess.run(["systemctl", "--user", "disable", "syncthingy.service"], check=True)
            else:
                subprocess.run(["systemctl", "--user", "enable", "syncthingy.service"], check=True)
                subprocess.run(["systemctl", "--user", "start", "syncthingy.service"], check=True)
            
            subprocess.run([
                "zenity", "--info",
                f"--text=SyncThingy {'activated' if not active else 'deactivated'}.\nRestart recommended.",
                "--timeout=2"
            ])
            return True
        except subprocess.CalledProcessError:
            subprocess.run([
                "zenity", "--error",
                "--text=Error changing service status",
                "--timeout=2"
            ])
    
    return False

def manage_sync_folders() -> List[str]:
    current_folders = []
    if os.path.exists(SYNC_FOLDERS_FILE):
        with open(SYNC_FOLDERS_FILE, 'r') as f:
            current_folders = [line.strip() for line in f if line.strip()]

    while True:
        choice = subprocess.run([
            'zenity', '--list',
            '--title=Sync Folders Management',
            '--text=Select an action:',
            '--column=Action',
            'Add folder',
            'Remove folder',
            '--hide-header',
            '--cancel-label=Exit'
        ], capture_output=True, text=True).stdout.strip()

        if not choice:
            break

        if choice == 'Add folder':
            new_folder = subprocess.run([
                'zenity', '--file-selection',
                '--title=Select folder to sync',
                '--directory'
            ], capture_output=True, text=True).stdout.strip()

            if new_folder and new_folder not in current_folders:
                current_folders.append(new_folder)
                with open(SYNC_FOLDERS_FILE, 'w') as f:
                    f.write("\n".join(current_folders))

        elif choice == 'Remove folder':
            if not current_folders:
                subprocess.run([
                    'zenity', '--info',
                    '--text=No folders to remove',
                    '--timeout=2'
                ])
                continue

            folders_formatted = "\n".join([f"FALSE\n{folder}" for folder in current_folders])
            selected = subprocess.run([
                'zenity', '--list',
                '--title=Select folders to remove',
                '--text=Check folders to remove:',
                '--column=Selection',
                '--column=Folder',
                '--checklist',
                '--separator=\n',
                '--multiple'
            ], input=folders_formatted, capture_output=True, text=True).stdout.strip()

            if selected:
                selected_folders = selected.split('\n')
                current_folders = [f for f in current_folders if f not in selected_folders]
                with open(SYNC_FOLDERS_FILE, 'w') as f:
                    f.write("\n".join(current_folders))

    return current_folders

def select_backup_directory():
    logger = logging.getLogger('GBM_Backup')
    
    config_file = ALTERNATIVE_BACKUPS_PATH_FILE

    zenity_command = [
        'zenity', '--list', '--title=Backup Directory Selection',
        '--text=Select an option:', '--column=Option',
        'Select custom directory',
        'Use default directory (/home/deck/Backups)',
        '--height=200', '--width=400'
    ]

    try:
        option = subprocess.check_output(zenity_command, text=True).strip()
        
        if option == 'Select custom directory':
            dir_dialog = ['zenity', '--file-selection', '--directory', 
                         '--title=Select backup directory']
            selected_dir = subprocess.check_output(dir_dialog, text=True).strip()
            
            with open(config_file, 'w') as f:
                f.write(selected_dir)
            logger.info(f"Selected directory saved: {selected_dir}")
            
        elif option == 'Use default directory (/home/deck/Backups)':
            if os.path.exists(config_file):
                os.remove(config_file)
                logger.info("Restored default directory")
            else:
                logger.info("Already using default directory")
                
    except subprocess.CalledProcessError:
        logger.info("Operation cancelled by user")

def with_zenity_progress(title, message):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            progress = subprocess.Popen([
                'zenity', '--progress',
                '--title=' + title,
                '--text=' + (message(*args, **kwargs) if callable(message) else message),
                '--no-cancel',
                '--pulsate',
                '--width=300'
            ], stdin=subprocess.PIPE, text=True)
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                progress.communicate("# Error occurred")
                raise e
            finally:
                progress.terminate()
                progress.wait()
        return wrapper
    return decorator