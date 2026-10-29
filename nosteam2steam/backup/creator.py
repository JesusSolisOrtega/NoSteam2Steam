"""Creation and packaging of game save backups into GBM-compliant archives."""

from datetime import datetime
from fnmatch import fnmatch
import logging
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

from nosteam2steam.config import ID_MAP_PATH, SCRIPT_DIR, STEAMDECK_PATH, get_backups_directory  # noqa: F401
from nosteam2steam.utils import compute_hash
from nosteam2steam.backup.path_converter import PathConverter, transform_path_from_windows_to_proton
from nosteam2steam.backup.archive import create_file_7z_gbm, process_filetype
from nosteam2steam.backup.inventory import load_games_mapping

logger = logging.getLogger(__name__)

__all__ = [
    "generate_config_id",
    "assign_os_code",
    "is_empty_folder",
    "filter_valid_paths",
    "get_valid_paths",
    "get_process_name",
    "normalize_name",
    "load_gbm_configs",
    "search_config_gbm",
    "clean_source_paths",
    "create_backup_gbm",
    "create_backup_from_gbm",
    "verify_and_create_missing_backup",
    "load_games_mapping",
]


def generate_config_id(game_name, config_save):
    """Generates deterministic UUIDv5 identifier for a game configuration."""
    unique_str = f"{game_name}_{config_save['meta_path']}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, unique_str))


def assign_os_code(when_conditions):
    """Maps Ludusavi OS conditions to Game Backup Monitor integer OS codes."""
    systems = set()
    for condition in when_conditions:
        if "os" in condition:
            systems.add(condition["os"])

    mapping = {
        "windows": 1,
        "linux": 2,
        "mac": 3,
    }
    if systems:
        first_system = next(iter(systems))
        return mapping.get(first_system, 1)
    return 1


def is_empty_folder(dir_path):
    """Verifies whether a directory contains any files."""
    try:
        return not any(file.is_file() for file in Path(dir_path).rglob("*"))
    except Exception as e:
        logger.error(f"Could not verify directory {dir_path}: {e}")
        return True


def filter_valid_paths(processed_paths):
    """Filters out nonexistent or empty directory targets."""
    filtered_paths = []

    for path_info in processed_paths:
        path = path_info["physical_path"]

        if not path.exists():
            logger.debug(f"Filtered out - Path does not exist: {path}")
            continue

        if path.is_dir():
            if is_empty_folder(path):
                logger.debug(f"Filtered out - Empty directory: {path}")
                continue
            logger.debug(f"Valid - Directory with content: {path}")
        else:
            logger.debug(f"Valid - File: {path}")

        filtered_paths.append(path_info)

    return filtered_paths


def get_valid_paths(game_data, alternative_appids=None):
    """Extracts and validates save paths from game data using PathConverter."""
    if not game_data.get("files"):
        logger.debug(f"Game {game_data.get('app_id_short')} has no defined paths")
        return []

    if alternative_appids:
        processed_paths = PathConverter.search_saves_on_alternative_appids(game_data, alternative_appids)
    else:
        processed_paths = PathConverter.process_game_entry(game_data)

    logger.debug(f"Processed {len(processed_paths)} initial paths")
    filtered_paths = filter_valid_paths(processed_paths)
    logger.info(f"✓ Game {game_data.get('app_id_short')}: {len(filtered_paths)} valid paths")

    return filtered_paths


def get_process_name(game_data):
    """Returns executable stem name or unknown."""
    exe_path = game_data.get("exe_path", "")
    return Path(exe_path).stem if exe_path else "unknown"


def normalize_name(name):
    """Normalizes title string for insensitive alphanumeric matching."""
    return re.sub(r"[^\w]", "", name.lower())


def load_gbm_configs(xml_path):
    """Parses GBM official configurations XML file into normalized dictionary."""
    configs = {}
    try:
        tree = ET.parse(xml_path)
        for game in tree.getroot().findall("Game"):
            name = game.findtext("Name")
            if not name:
                continue
            exclude_text = game.findtext("ExcludeList") or ""
            file_type_text = game.findtext("FileType") or ""
            os_elem = game.findtext("OS")
            configs[normalize_name(name)] = {
                "original_name": name,
                "GBM_ID": game.findtext("ID") or "",
                "ProcessName": game.findtext("ProcessName") or "",
                "windows_path": game.findtext("Path") or "",
                "is_folder": (game.findtext("FolderSave") or "").lower() == "true",
                "Tags": [tag.text or "" for tag in game.findall("Tags/Tag") if tag.text],
                "OS": int(os_elem) if os_elem and os_elem.isdigit() else 1,
                "ExcludeList": exclude_text,
                "FileType": file_type_text,
            }
    except Exception as e:
        logger.error(f"Error loading GBM_Official.xml: {e}")
    return configs


def search_config_gbm(game_name, gbm_configs):
    """Searches GBM configuration dictionary for exact or normalized game match."""
    original_clean_name = game_name.strip().lower()
    norm_name = normalize_name(game_name)

    for config in gbm_configs.values():
        original_name_config = config["original_name"].lower()
        config_name_norm = normalize_name(config["original_name"])

        if original_clean_name == original_name_config:
            logger.debug(f"Exact match found for: {game_name}")
            return config

        if norm_name == config_name_norm:
            logger.debug(f"Normalized match found for: {game_name}")
            return config

    logger.debug(f"No matches found for: {game_name}")
    return None


def clean_source_paths(source_paths, exclude_list):
    """Filters out files or directories matching patterns in exclude_list."""
    if not exclude_list or not source_paths:
        return source_paths

    exclude_patterns = exclude_list.split(":")
    filtered_paths = []

    for path in source_paths:
        if path.is_dir():
            included_files = []
            for item in path.rglob("*"):
                if item.is_file():
                    exclude = any(fnmatch(item.name, pattern) for pattern in exclude_patterns)
                    if not exclude:
                        included_files.append(item)

            if included_files:
                filtered_paths.append(path)
        else:
            exclude = any(fnmatch(path.name, pattern) for pattern in exclude_patterns)
            if not exclude:
                filtered_paths.append(path)

    return filtered_paths


def create_backup_gbm(game_name, config_save, process_name, backup_root_dir):
    """Creates a Ludusavi-based save backup archived in 7z format."""
    config_id = generate_config_id(game_name, config_save)
    folder_name = f"{game_name} [{config_id}]"
    file_name = f"{game_name} [{config_id}].7z"

    backup_dir = backup_root_dir / folder_name
    backup_dir.mkdir(parents=True, exist_ok=True)

    origin_path = config_save["physical_path"]
    source_paths = [origin_path]

    try:
        file_7z = create_file_7z_gbm(
            source_paths=source_paths,
            metadata={
                "config_id": config_id,
                "game_name": game_name,
                "process_name": process_name,
                "original_path": config_save["original_path"],
                "meta_path": config_save["meta_path"],
                "is_folder": origin_path.is_dir(),
                "os_code": assign_os_code(config_save.get("when", [])),
                "tags": ["Ludusavi"],
                "ExcludeList": "",
                "FileType": "",
            },
            target_dir=backup_dir,
            file_name=file_name,
        )

        return {
            "backup_file": file_7z,
            "original_path": origin_path,
            "backup_path": backup_dir,
            "config_id": config_id,
        }
    except Exception as e:
        logger.error(f"Error in create_backup_gbm: {e}")
        raise


def create_backup_from_gbm(game_name, gbm_config, backup_root_dir, game_data=None, alternative_appids=None):
    """Creates a GBM configuration-based backup archive."""
    try:
        proton_path = transform_path_from_windows_to_proton(gbm_config["windows_path"], game_data, STEAMDECK_PATH)

        is_folder = gbm_config.get("is_folder", False)
        file_type = gbm_config.get("FileType", "")
        exclude_list = gbm_config.get("ExcludeList", "")
        source_paths = []

        if alternative_appids and game_data:
            original_appid = game_data["app_id_short"]
            for alt_appid in alternative_appids:
                alternative_path = Path(str(proton_path).replace(original_appid, alt_appid))
                if alternative_path.exists():
                    if alternative_path.is_dir() and is_empty_folder(alternative_path):
                        continue
                    logger.debug(f"Alternative path found: {alternative_path}")
                    proton_path = alternative_path
                    break

        if is_folder:
            if proton_path.exists() and proton_path.is_dir():
                if is_empty_folder(proton_path):
                    logger.warning(f"Empty directory: {proton_path}")
                    return None
                source_paths = list(proton_path.glob("*"))
        else:
            if file_type:
                target_base = proton_path.parent if proton_path.is_file() else proton_path
                source_paths = process_filetype(target_base, file_type)
                if not source_paths:
                    logger.warning(f"No files found matching FileType: {file_type}")
                    return None
            elif proton_path.exists() and proton_path.is_file():
                source_paths = [proton_path]

        if source_paths and exclude_list:
            source_paths = clean_source_paths(source_paths, exclude_list)

        if not source_paths:
            logger.warning(f"No valid files found for {game_name}")
            return None

        metadata = {
            **gbm_config,
            "config_id": gbm_config["GBM_ID"],
            "game_name": gbm_config["original_name"],
            "original_path": gbm_config["windows_path"],
            "meta_path": gbm_config["windows_path"],
            "is_folder": is_folder,
        }

        file_7z = create_file_7z_gbm(
            source_paths=source_paths,
            metadata=metadata,
            target_dir=backup_root_dir / gbm_config["original_name"],
            file_name=f"{gbm_config['original_name']}.7z",
        )

        return {
            "backup_file": file_7z,
            "original_path": proton_path,
            "config_id": gbm_config["GBM_ID"],
            "source": "GBM_Official",
        }
    except Exception as e:
        logger.error(f"Error creating GBM backup: {e}")
        return None


def verify_and_create_missing_backup(
    game_name, game_mapping, inventory, record, alternative_appids=None, gbm_configs=None
):
    """Verifies existing backup state and creates backup if absent from inventory."""
    if game_name in inventory:
        logger.debug(f"Game {game_name} already in inventory")
        return False

    backups_path = get_backups_directory()
    game_data = game_mapping.get(game_name)

    if gbm_configs is None:
        gbm_configs = load_gbm_configs(SCRIPT_DIR / "GBM_Official.xml")
    if gbm_config := search_config_gbm(game_name, gbm_configs):
        logger.info(f"✓ GBM configuration found for {game_name}")
        if result := create_backup_from_gbm(game_name, gbm_config, backups_path, game_data, alternative_appids):
            if alternative_appids or not isinstance(record, dict):
                logger.info(f"Backup created from alternative path: {result['backup_file']}")
                return True
            else:
                record.setdefault(game_name, {})[str(result["backup_file"])] = {
                    "last_sync": datetime.now().isoformat(),
                    "updated_from": "local",
                    "hash_backup": compute_hash(result["backup_file"]),
                    "hash_local": compute_hash(result["original_path"]),
                    "source": "GBM_Official",
                }
                logger.info(f"Backup creado: {result['backup_file']}")
                return True

    if not game_data or not game_data.get("files"):
        logger.debug(f"Juego {game_name} has no valid data")
        return False

    process_name = get_process_name(game_data)
    paths_with_info = get_valid_paths(game_data, alternative_appids)

    if not paths_with_info:
        logger.info(f"✗ Game {game_name}: No valid paths")
        return False

    successes = 0
    for config_save in paths_with_info:
        try:
            result = create_backup_gbm(
                game_name=game_name,
                config_save=config_save,
                process_name=process_name,
                backup_root_dir=backups_path,
            )
            if result:
                if not alternative_appids and isinstance(record, dict):
                    record.setdefault(game_name, {})[str(result["backup_file"])] = {
                        "last_sync": datetime.now().isoformat(),
                        "updated_from": "local",
                        "hash_backup": compute_hash(result["backup_file"]),
                        "hash_local": compute_hash(config_save["physical_path"]),
                        "source": "Ludusavi",
                    }
                successes += 1
                logger.info(f"Backup created: {result['backup_file']} from {config_save['physical_path']}")
        except Exception as e:
            logger.error(f"Error in {game_name}: {str(e)}", exc_info=True)

    logger.info(f"► Game {game_name}: {successes}/{len(paths_with_info)} backups created")
    return successes > 0
