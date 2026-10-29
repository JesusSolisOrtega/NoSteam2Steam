"""General-purpose utilities, cryptographic hashing, and execution wrappers."""

from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import hashlib
import logging
import os
from pathlib import Path
import subprocess
import time

from nosteam2steam import ui
from nosteam2steam.services import (
    is_service_active,
    is_service_enabled,
    manage_syncthingy_service,
)
from nosteam2steam.dialogs import (
    delete_current_config,
    delete_games_images,
    manage_sync_folders,
    select_backup_directory,
    show_cleanup_dialog,
)

logger = logging.getLogger(__name__)


def compute_hash(path, max_workers=None, size_threshold=100 * 1024 * 1024):
    """Calculates BLAKE2b/SHA digest hash for a file or directory tree."""
    path = Path(path)
    try:
        if path.is_file():
            return _hash_file(path, size_threshold)
        elif path.is_dir():
            return _hash_dir(path, max_workers, size_threshold)
    except Exception as e:
        logger.error(f"Error calculating hash: {path} - {str(e)}")
        return None


def _hash_file(file_path, size_threshold, sample_size=1 * 1024 * 1024):
    hasher = hashlib.blake2b(digest_size=32)
    try:
        stat = file_path.stat()
        file_size = stat.st_size
        mtime = stat.st_mtime_ns

        with open(file_path, "rb") as f:
            if file_size <= size_threshold:
                for block in iter(lambda: f.read(128 * 1024), b""):
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


def _hash_dir(dir_path, max_workers=None, size_threshold=150 * 1024 * 1024):
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
            with open(file_path, "rb") as f:
                if file_size <= size_threshold:
                    for block in iter(lambda: f.read(128 * 1024), b""):
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
            return b"\x00" * 32

    with ThreadPoolExecutor(max_workers=max_workers or os.cpu_count()) as executor:
        for file_hash in executor.map(process_file, files):
            hasher.update(file_hash)

    return hasher.hexdigest()


def is_steamdeck_gamemode() -> bool:
    """Detects whether running inside SteamOS Gamescope Game Mode session."""
    return (
        os.environ.get("XDG_CURRENT_DESKTOP", "").lower() == "gamescope"
        or os.environ.get("SteamGamepadUI") == "1"
    )


def ensure_steam_closed() -> bool:
    """
    Checks if Steam is running. In SteamOS Desktop Mode, modifying shortcuts.vdf
    while Steam is open often causes Steam to overwrite shortcuts with its in-memory state on exit.
    Prompts the user to close Steam gracefully if running in Desktop Mode.
    In Game Mode, shutdown is skipped to avoid killing the active session.
    """
    if is_steamdeck_gamemode():
        logger.info("Running in SteamOS Game Mode; skipping steam shutdown to preserve session.")
        return True

    try:
        res = subprocess.run(["pgrep", "-x", "steam"], capture_output=True, text=True)
        if res.returncode == 0:
            should_close = ui.ask_question(
                title="Steam is running",
                text="Steam is currently running in the background.\n\n"
                "To ensure new games are saved properly to shortcuts.vdf, Steam should be closed.\n\n"
                "Do you want to close Steam now?",
                ok_label="Close Steam",
                cancel_label="Continue anyway",
                width=400,
            )
            if should_close:
                with ui.progress_dialog(title="Steam", text="Cerrando cliente Steam de forma ordenada..."):
                    subprocess.run(["steam", "-shutdown"])
                    for _ in range(8):
                        time.sleep(1)
                        if subprocess.run(["pgrep", "-x", "steam"], capture_output=True).returncode != 0:
                            break
                logger.info("Steam shutdown initiated.")
            else:
                logger.warning("User chose to keep Steam running while modifying shortcuts.")
        return True
    except Exception as e:
        logger.error(f"Error checking Steam process: {e}")
        return True


def with_zenity_progress(title, message):
    """Decorator to display pulsating progress window during function execution with multi-backend support."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            text_val = str(message(*args, **kwargs)) if callable(message) else str(message)
            with ui.progress_dialog(title=str(title), text=text_val, pulsate=True):
                return func(*args, **kwargs)

        return wrapper

    return decorator

    return decorator


__all__ = [
    "compute_hash",
    "ensure_steam_closed",
    "with_zenity_progress",
    "is_service_active",
    "is_service_enabled",
    "manage_syncthingy_service",
    "delete_current_config",
    "delete_games_images",
    "show_cleanup_dialog",
    "manage_sync_folders",
    "select_backup_directory",
]
