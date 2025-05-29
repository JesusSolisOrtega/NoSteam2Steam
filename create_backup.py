from datetime import datetime
import re
from fnmatch import fnmatch
import time
import json
from pathlib import Path
import uuid
from path_converter import PathConverter, transform_path_from_windows_to_proton
import py7zr
import xml.etree.ElementTree as ET

from config import ID_MAP_PATH, SCRIPT_DIR, COMPATDATA_PATH, get_backups_directory
from utils import compute_hash

import logging


logger = logging.getLogger('GBM_Backup')

def create_file_7z_gbm(source_paths, metadata, target_dir, file_name):
    target_dir.mkdir(parents=True, exist_ok=True)
    file_7z = target_dir / file_name

    root = ET.Element("GBM_Backup")
    root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("AppVer", "141")

    backup_data = ET.SubElement(root, "BackupData")
    ET.SubElement(backup_data, "ManifestID").text = str(uuid.uuid4())
    ET.SubElement(backup_data, "DateUpdated").text = str(int(time.time()))
    ET.SubElement(backup_data, "UpdatedBy").text = "GBM_PYTHON_TOOL"
    ET.SubElement(backup_data, "IsDifferentialParent").text = "false"
    ET.SubElement(backup_data, "DifferentialParent")

    game_data = ET.SubElement(root, "GameData")
    fields = {
        "ID": metadata["config_id"],
        "Name": metadata["game_name"],
        "ProcessName": metadata["process_name"],
        "Parameter": "",
        "Path": metadata["meta_path"],
        "FolderSave": "true" if metadata["is_folder"] else "false",
        "AppendTimeStamp": "false",
        "BackupLimit": "0",
        "FileType": metadata["FileType"] if metadata["FileType"] else "",
        "ExcludeList": metadata["ExcludeList"] if metadata["ExcludeList"] else "",
        "MonitorOnly": "false",
        "Comments": "",
        "IsRegEx": "false",
        "RecurseSubFolders": "true",
        "OS": str(metadata["os_code"]),
        "UseWindowTitle": "false",
        "Differential": "false",
        "DiffInterval": "0"
    }

    for tag, value in fields.items():
        elem = ET.SubElement(game_data, tag)
        if str(value):
            elem.text = str(value)

    if "tags" in metadata and metadata["tags"]:
        tags_elem = ET.SubElement(game_data, "Tags")
        for tag in metadata["tags"]:
            tag_elem = ET.SubElement(tags_elem, "Tag")
            ET.SubElement(tag_elem, "Name").text = tag

    ET.SubElement(game_data, "ConfigLinks")

    def indent(elem, level=0):
        indent_str = "  " * level
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = f"\n{indent_str}  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = f"\n{indent_str}"
            for child in elem:
                indent(child, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = f"\n{indent_str}"
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = f"\n{indent_str}"

    indent(root)

    temp_xml_path = Path(f"temp_gbm_meta_{uuid.uuid4().hex}.xml")
    try:
        with open(temp_xml_path, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            ET.ElementTree(root).write(f, encoding='utf-8')

        with py7zr.SevenZipFile(file_7z, 'w') as z:
            for source_path in source_paths:
                if source_path.is_dir():
                    for item_path in source_path.rglob('*'):
                        arcname = str(item_path.relative_to(source_path))
                        z.write(item_path, arcname=arcname)
                else:
                    z.write(source_path, arcname=source_path.name)

            z.write(temp_xml_path, arcname="_gbm_backup_metadata.xml")

    except Exception as e:
        logger.error(f"Error creating 7z file: {e}")
        if file_7z.exists():
            file_7z.unlink()
        raise
    finally:
        temp_xml_path.unlink(missing_ok=True)

    return file_7z

def create_backup_gbm(game_name, config_save, process_name, backup_root_dir):
    config_id = generate_config_id(game_name, config_save)
    folder_name = f"{game_name} [{config_id}]"
    file_name = f"{game_name} [{config_id}].7z"

    backup_dir = backup_root_dir / folder_name
    backup_dir.mkdir(parents=True, exist_ok=True)

    origin_path = config_save['physical_path']
    source_paths = []
    if origin_path.is_dir():
        source_paths = [origin_path]
    else:
        source_paths = [origin_path]

    try:
        file_7z = create_file_7z_gbm(
            source_paths=source_paths,
            metadata={
                "config_id": config_id,
                "game_name": game_name,
                "process_name": process_name,
                "original_path": config_save['original_path'],
                "meta_path": config_save['meta_path'],
                "is_folder": origin_path.is_dir(),
                "os_code": assign_os_code(config_save.get('when', [])),
                "tags": ["Ludusavi"],
                "ExcludeList": '',
                "FileType": ''
            },
            target_dir=backup_dir,
            file_name=file_name
        )

        return {
            'backup_file': file_7z,
            'original_path': origin_path,
            'backup_path': backup_dir,
            'config_id': config_id
        }
    except Exception as e:
        logger.error(f"Error in create_backup_gbm: {e}")
        raise

def generate_config_id(game_name, config_save):
    unique_str = f"{game_name}_{config_save['meta_path']}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, unique_str))

def assign_os_code(when_conditions):
    systems = set()
    for condition in when_conditions:
        if 'os' in condition:
            systems.add(condition['os'])

    return {
        'windows': 1,
        'linux': 2,
        'mac': 3
    }.get(next(iter(systems), 0) if systems else 1 )
def is_empty_folder(dir_path):
    try:
        return not any(file.is_file() for file in dir_path.rglob('*'))
    except Exception as e:
        logger.error(f"Could not verify directory {dir_path}: {e}")
        return True

def filter_valid_paths(processed_paths):
    filtered_paths = []

    for path_info in processed_paths:
        path = path_info['physical_path']

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
    if not game_data.get('files'):
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
    exe_path = game_data.get("exe_path", "")
    return Path(exe_path).stem if exe_path else "unknown"

def normalize_name(name):
    return re.sub(r'[^\w]', '', name.lower())

def load_gbm_configs(xml_path):
    configs = {}
    try:
        tree = ET.parse(xml_path)
        for game in tree.getroot().findall('Game'):
            name = game.find('Name').text
            exclude_elem = game.find('ExcludeList')
            configs[normalize_name(name)] = {
                'original_name': name,
                'GBM_ID': game.find('ID').text,
                'ProcessName': game.find('ProcessName').text or "",
                'windows_path': game.find('Path').text,
                'is_folder': game.find('FolderSave').text.lower() == 'true',
                'Tags': [tag.find('Name').text for tag in game.findall('Tags/Tag')],
                'OS': int(game.find('OS').text) if game.find('OS') is not None else 1,
                'ExcludeList': exclude_elem.text if exclude_elem is not None else "",
                'FileType': game.find('FileType').text if game.find('FileType') is not None else ""
            }
    except Exception as e:
        logger.error(f"Error loading GBM_Official.xml: {e}")
    return configs

def search_config_gbm(game_name, gbm_configs):
    original_clean_name = game_name.strip().lower()
    norm_name = normalize_name(game_name)

    for config in gbm_configs.values():
        original_name_config = config['original_name'].lower()
        config_name_norm = normalize_name(config['original_name'])

        if original_clean_name == original_name_config:
            logger.debug(f"Exact match found for: {game_name}")
            return config

        if norm_name == config_name_norm:
            logger.debug(f"Normalized match found for: {game_name}")
            return config

    logger.debug(f"No matches found for: {game_name}")
    return None

def clean_source_paths(source_paths, exclude_list):
    if not exclude_list or not source_paths:
        return source_paths

    exclude_patterns = exclude_list.split(':')

    filtered_paths = []
    for path in source_paths:
        if path.is_dir():
            included_files = []
            for item in path.rglob('*'):
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

def create_backup_from_gbm(game_name, gbm_config, backup_root_dir, game_data=None, alternative_appids=None):
    try:

        proton_path = transform_path_from_windows_to_proton(
            gbm_config['windows_path'],
            game_data,
            COMPATDATA_PATH
        )

        is_folder = gbm_config.get('is_folder', False)
        file_type = gbm_config.get('FileType', '')
        exclude_list = gbm_config.get('ExcludeList', '')
        source_paths = []

        if alternative_appids:
            original_appid = game_data['app_id_short']
            for alt_appid in alternative_appids:
                alternative_path = Path(str(proton_path).replace(original_appid, alt_appid))
                if alternative_path.exists():
                    if alternative_path.is_dir():
                        if is_empty_folder(alternative_path):
                            continue

                    logger.debug(f"Alternative path found: {alternative_path}")
                    proton_path = alternative_path
                    break

        if is_folder:
            if proton_path.exists() and proton_path.is_dir():
                if is_empty_folder(proton_path):
                    logger.warning(f"Empty directory: {proton_path}")
                    return None

                source_paths = list(proton_path.glob('*'))
        else:
            if file_type:
                source_paths = process_filetype(proton_path.parent if proton_path.is_file() else proton_path, file_type)
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
            "config_id": gbm_config['GBM_ID'],
            "game_name": gbm_config['original_name'],
            "original_path": gbm_config['windows_path'],
            "meta_path": gbm_config['windows_path'],
            "is_folder": is_folder,
        }

        file_7z = create_file_7z_gbm(
            source_paths=source_paths,
            metadata=metadata,
            target_dir=backup_root_dir / gbm_config['original_name'],
            file_name=f"{gbm_config['original_name']}.7z"
        )

        return {
            'backup_file': file_7z,
            'original_path': proton_path,
            'config_id': gbm_config['GBM_ID'],
            'source': 'GBM_Official'
        }
    except Exception as e:
        logger.error(f"Error creating GBM backup: {e}")
        return None

def process_filetype(base_folder, file_type):
    matching_files = []

    patterns = file_type.split(':') if ':' in file_type else [file_type]

    for pattern in patterns:
        if ':' in pattern and '*' not in pattern:
            file, subdir = pattern.split(':', 1)
            search_path = base_folder / subdir.strip()
            if search_path.exists() and (search_path / file.strip()).exists():
                matching_files.append(search_path / file.strip())
            continue

        if '*' in pattern and ('/' in pattern or '\\' in pattern):
            folder_part, file_part = pattern.replace('\\', '/').rsplit('/', 1)
            for match_dir in base_folder.glob(folder_part):
                if match_dir.is_dir():
                    for file in match_dir.glob(file_part):
                        if file.is_file() and fnmatch(file.name, file_part):
                            matching_files.append(file)
            continue

        for file in base_folder.glob(pattern):
            if file.is_file() and fnmatch(file.name, pattern):
                matching_files.append(file)

    return list(set(matching_files))

def verify_and_create_missing_backup(game_name, game_mapping, inventory, record, alternative_appids=None):
    if game_name in inventory:
        logger.debug(f"Game {game_name} already in inventory")
        return False

    backups_path = get_backups_directory()
    game_data = game_mapping.get(game_name)

    gbm_configs = load_gbm_configs(SCRIPT_DIR / 'GBM_Official.xml')
    if gbm_config := search_config_gbm(game_name, gbm_configs):
        logger.info(f"✓ GBM configuration found for {game_name}")
        if result := create_backup_from_gbm(game_name, gbm_config, backups_path, game_data, alternative_appids):
            if alternative_appids:
                logger.info(f"Backup created from alternative path: {result['backup_file']}")
                return True  
            else:
                record.setdefault(game_name, {})[str(result['backup_file'])] = {
                    "last_sync": datetime.now().isoformat(),
                    "updated_from": "local",
                    "hash_backup": compute_hash(result['backup_file']),
                    "hash_local": compute_hash(result['original_path']),
                    "source": "GBM_Official"
                }
                logger.info(f"Backup creado: {result['backup_file']}")
                return True

    if not game_data or not game_data.get('files'):
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
                backup_root_dir=backups_path
            )
            if result:
                if not alternative_appids:
                    record.setdefault(game_name, {})[str(result['backup_file'])] = {
                        "last_sync": datetime.now().isoformat(),
                        "updated_from": "local",
                        "hash_backup": compute_hash(result['backup_file']),
                        "hash_local": compute_hash(config_save['physical_path']),
                        "source": "Ludusavi"
                    }
                successes += 1
                logger.info(f"Backup created: {result['backup_file']} from {config_save['physical_path']}")
        except Exception as e:
            logger.error(f"Error in {game_name}: {str(e)}", exc_info=True)
    
    logger.info(f"► Game {game_name}: {successes}/{len(paths_with_info)} backups created")
    return successes > 0

def load_games_mapping(path_id_map=ID_MAP_PATH):
    try:
        with open(path_id_map, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Error loading JSON file: {e}")
        return None
