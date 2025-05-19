#identify_game.py
from collections import deque
import logging
import os
import xml.etree.ElementTree as ET
import yaml
from yaml import CSafeLoader as SafeLoader
import io
import requests
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import json
import re
from pathlib import Path
import platform
import time
from typing import Dict, List, Optional, Set, Any

from config import GOG_PATHS, HEROIC_PATHS, DEFAULT_SYNC_FOLDER, IGNORED_FILES, IGNORED_DIRS, XML_FILE, YAML_FILE, XML_URL, YAML_URL, SYNC_FOLDERS_FILE, INDEX_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("no_steam_to_steam.log")

def download_file(url, destination):
    try:
        response = requests.head(url, allow_redirects=True)
        response.raise_for_status()

        remote_last_modified = response.headers.get("Last-Modified")
        remote_etag = response.headers.get("ETag")

        if os.path.exists(destination):
            if remote_last_modified:
                local_last_modified = time.ctime(os.path.getmtime(destination))
                if remote_last_modified <= local_last_modified:
                    logger.info(f"File {destination} has not changed (Last-Modified).")
                    return False
            if remote_etag:
                etag_file = destination + ".etag"
                if os.path.exists(etag_file):
                    with open(etag_file, "r") as f:
                        local_etag = f.read().strip()
                        if remote_etag == local_etag:
                            logger.info(f"File {destination} has not changed (ETag).")
                            return False

        response = requests.get(url)
        response.raise_for_status()
        with open(destination, "wb") as file:
            file.write(response.content)
        logger.info(f"File downloaded and saved to: {destination}")

        if remote_etag:
            with open(destination + ".etag", "w") as f:
                f.write(remote_etag)

        return True
    except requests.RequestException as e:
        logger.error(f"Error downloading file: {e}")
        return False

def load_yaml_file(file_path):
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
            
            try:
                return yaml.load(io.BytesIO(data), Loader=SafeLoader)
            except:
                return yaml.safe_load(data.decode('utf-8'))
                
    except Exception as e:
        logger.error(f"Error loading YAML: {str(e)[:200]}")
        return None

def index_xml_data(root):
    xml_index = {}
    for game in root.findall('Game'):
        game_name = game.find('Name').text if game.find('Name') is not None else None
        process_name = game.find('ProcessName').text if game.find('ProcessName') is not None else None
        if game_name and process_name:
            xml_index[process_name.lower()] = game_name
    return xml_index

def normalize_path(path):
    return os.path.normpath(path).replace("\\", "/").lower()

def is_64bit_system():
    return sys.maxsize > 2**32

def index_yaml_data(yaml_data: Dict) -> Dict:
    index = {
        "_metadata": [],  
        "by_exe": {},
        "by_path": {},
        "by_install_dir": {},
        "by_gog_id": {},
        "by_steam_id": {},
        "by_name": {}, 
        "by_name_fuzzy": {} 
    }
    
    index["_metadata"] = [None] * len(yaml_data)
    
    for yaml_game_name, yaml_game_data in yaml_data.items():
        metadata = {
            "game_name": yaml_game_name,
            "steam_id": yaml_game_data.get("steam", {}).get("id"),
            "lutris_id": yaml_game_data.get("id", {}).get("lutris"),
            "gog_id": yaml_game_data.get("gog", {}).get("id"),
            "alias": yaml_game_data.get("alias"),
            "files": yaml_game_data.get("files", {})
        }
        
        metadata_str = json.dumps(metadata, sort_keys=True)
        if metadata_str not in getattr(index_yaml_data, '_cache', {}):
            if not hasattr(index_yaml_data, '_cache'):
                index_yaml_data._cache = {}
            meta_idx = len(index["_metadata"])
            index["_metadata"].append(metadata)
            index_yaml_data._cache[metadata_str] = meta_idx
        else:
            meta_idx = index_yaml_data._cache[metadata_str]

        normalized_name = yaml_game_name.lower()
        index["by_name"][normalized_name] = meta_idx
        
        name_parts = set(normalized_name.split())
        for part in name_parts:
            if len(part) > 2: 
                if part not in index["by_name_fuzzy"]:
                    index["by_name_fuzzy"][part] = []
                index["by_name_fuzzy"][part].append(meta_idx)
        
        if metadata["alias"]:
            if isinstance(metadata["alias"], str):
                aliases = [metadata["alias"]]
            else:
                aliases = metadata["alias"]
            
            for alias in aliases:
                normalized_alias = alias.lower()
                index["by_name"][normalized_alias] = meta_idx
                alias_parts = set(normalized_alias.split())
                for part in alias_parts:
                    if len(part) > 2:
                        if part not in index["by_name_fuzzy"]:
                            index["by_name_fuzzy"][part] = []
                        index["by_name_fuzzy"][part].append(meta_idx)

        if metadata["steam_id"]:
            index["by_steam_id"][str(metadata["steam_id"])] = meta_idx
            
        if metadata["gog_id"]:
            index["by_gog_id"][str(metadata["gog_id"])] = meta_idx

        if "installDir" in yaml_game_data:
            install_dir = (yaml_game_data["installDir"].lower() 
                        if isinstance(yaml_game_data["installDir"], str) 
                        else next(iter(yaml_game_data["installDir"].keys()), "").lower())
            index["by_install_dir"][install_dir] = {
                "_meta": meta_idx,
                "launch": yaml_game_data.get("launch", {})
            }

        launch_data = yaml_game_data.get("launch", {})
        for launch_path in launch_data:
            if launch_path.startswith("<base>/"):
                path_key = launch_path[7:].lower()
                index["by_path"][path_key] = meta_idx
            
            exe_name = os.path.basename(launch_path).lower()
            if exe_name:
                index["by_exe"][exe_name] = meta_idx
    
    if hasattr(index_yaml_data, '_cache'):
        del index_yaml_data._cache
        
    return index

def save_index_to_file(index: Dict, file_path: str) -> None:
    try:
        with open(file_path, "w", encoding="utf-8", buffering=2**18) as file: 
            json.dump(
                index,
                file,
                ensure_ascii=False,
                separators=(',', ':'),
                check_circular=False,
                allow_nan=False
            )
    except Exception as e:
        logger.error(f"Critical error saving {file_path}: {str(e)[:200]}...")

def load_index_from_file(file_path: str) -> Optional[Dict]:
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Error loading index from {file_path}: {e}")
        return None

def supports_vulkan():
    try:
        result = subprocess.run(["vulkaninfo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.returncode == 0
    except FileNotFoundError:
        try:
            vulkan_drivers_path = "/usr/share/vulkan/icd.d"
            return os.path.exists(vulkan_drivers_path) and len(os.listdir(vulkan_drivers_path)) > 0
        except Exception:
            return False

def is_steamos():
    steamos_files = [
        "/usr/share/steamos", 
        "/home/deck", 
    ]
    is_steamos = False
    try:
        for file in steamos_files:
            if os.path.exists(file):
                is_steamos = True
    except Exception as e:
        logger.error(f"Error checking specific files: {e}")
    logger.info("\nIs steamOS:"+str(is_steamos)+"\n")
    return is_steamos

def path_exists_case_insensitive(path, dir_cache):
    p = Path(path)
    if p.exists():
        return str(p)
    
    current = Path(p.root) if p.is_absolute() else Path(".")
    for part in p.parts[p.is_absolute():]:
        if str(current) not in dir_cache:
            dir_cache[str(current)] = list(current.iterdir())  
        
        matches = [child for child in dir_cache[str(current)] if child.name.lower() == part.lower()]
        if not matches:
            return False
        current = matches[0]  
    
    return str(current)

def generate_alternative_paths(relative_path):
    arch_pattern = re.compile(r'(x64|x86|x64vk|x86vk|win64|win32)', re.IGNORECASE)
    
    path_without_ext, ext = os.path.splitext(relative_path) 
    matches = arch_pattern.findall(path_without_ext)
    
    if not matches:
        return [relative_path]  
    
    alternative_paths = set()  
    for match in matches:
        if match.lower() in ['x64', 'win64', 'x64vk', 'x86', 'win32', 'x86vk']:
            alternative_paths.add(path_without_ext.replace(match, 'x64') + ext)
            alternative_paths.add(path_without_ext.replace(match, 'x86') + ext)
            alternative_paths.add(path_without_ext.replace(match, 'win64') + ext) 
            alternative_paths.add(path_without_ext.replace(match, 'win32') + ext)
            alternative_paths.add(path_without_ext.replace(match, 'x64vk') + ext)
            alternative_paths.add(path_without_ext.replace(match, 'x86vk') + ext)
    
    return list(alternative_paths)

def select_best_path(relative_path, base_path):
    dir_cache = {}

    possible_paths = generate_alternative_paths(relative_path)
    
    is_64bit = is_64bit_system()
    
    supports_vk = supports_vulkan() or is_steamos()
    
    valid_paths = []

    for path in possible_paths:
        full_path = os.path.join(base_path, path)
        logger.info(f"Checking path: {full_path}")
        right_path = path_exists_case_insensitive(full_path, dir_cache)
        if right_path and os.path.isfile(right_path):
            logger.info("Valid path found.")
            valid_paths.append(right_path)
    
    if not valid_paths:
        return None 
    
    best_path = None
    for path in valid_paths:
        path_lower = path.lower()
        if supports_vk and 'vk' in path_lower:
            if is_64bit and ('x64' in path_lower or 'win64' in path_lower):
                return path
            elif not is_64bit and ('x86' in path_lower or 'win32' in path_lower):
                return path
            best_path = path if best_path is None else best_path
        elif is_64bit and ('x64' in path_lower or 'win64' in path_lower):
            best_path = path if best_path is None else best_path
        elif not is_64bit and ('x86' in path_lower or 'win32' in path_lower):
            best_path = path if best_path is None else best_path
    
    return best_path if best_path is not None else valid_paths[0]

def sort_launch_paths(launch_paths):
    current_os = platform.system().lower() 
    is_64bit = is_64bit_system()  
    
    prioritized_paths = []
    
    for path, conditions in launch_paths.items():
        if current_os in ['windows', 'linux']:
            if path.endswith('.app'):
                continue
                
            is_mac_only = False
            for condition in conditions:
                if isinstance(condition, dict) and "when" in condition:
                    for when in condition["when"]:
                        if isinstance(when, dict) and when.get("os", "").lower() == "mac":
                            is_mac_only = True
                            break
                if is_mac_only:
                    break
            if is_mac_only:
                continue
        
        priority = 2 
        
        for condition in conditions:
            if isinstance(condition, dict) and "when" in condition:
                for when in condition["when"]:
                    if not isinstance(when, dict):
                        continue
                    if (when.get("os", "").lower() == current_os and 
                        str(when.get("bit", "")) == ("64" if is_64bit else "32")):
                        priority = 0  
                        break
                    elif when.get("os", "").lower() == current_os:
                        priority = min(priority, 1)  
        
        prioritized_paths.append((path, priority))
    
    prioritized_paths.sort(key=lambda x: x[1])
    
    return [path for path, _ in prioritized_paths]

class DirectoryCache:
    def __init__(self):
        self._cache = {}
        
    def get_directory_contents(self, path):
        normalized_path = os.path.normcase(os.path.normpath(path))
        
        if normalized_path not in self._cache:
            try:
                contents = {
                    'dirs': [],
                    'files': []
                }
                with os.scandir(normalized_path) as it:
                    for entry in it:
                        if entry.is_dir():
                            contents['dirs'].append(entry.name)
                        else:
                            contents['files'].append(entry.name)
                self._cache[normalized_path] = contents
            except (OSError, PermissionError):
                self._cache[normalized_path] = {
                    'dirs': [],
                    'files': []
                }
        
        return self._cache[normalized_path]
    
    def clear(self):
        self._cache.clear()

def find_root_directory(sync_folder: str, yaml_index_by_install_dir: dict, dir_cache: DirectoryCache, excluded_folders: set = None) -> dict:
    if excluded_folders is None:
        excluded_folders = set()

    matches = {}
    try:
        with ThreadPoolExecutor() as executor:
            futures = []
            for root_folder in os.listdir(sync_folder):
                if root_folder.lower() in excluded_folders:
                    continue

                root_folder_path = os.path.join(sync_folder, root_folder)

                if os.path.isdir(root_folder_path):
                    futures.append(executor.submit(process_root_folder, root_folder_path, root_folder, yaml_index_by_install_dir, dir_cache))
            
            for future in futures:
                result = future.result()
                if result:
                    matches.update(result)
    
    except Exception as e:
        logger.error(f"Error searching root directories: {str(e)}")
    
    return matches

def process_root_folder(root_folder_path, root_folder, yaml_index_by_install_dir, dir_cache):
    result = {}
    stack = [(root_folder_path, 0, True)]
    
    while stack:
        current_path, depth, is_first_visit = stack.pop()
        
        if depth > 3:
            continue
        
        if is_first_visit:
            contents = dir_cache.get_directory_contents(current_path)
            current_dir = os.path.basename(current_path).lower()
            
            if current_dir in yaml_index_by_install_dir:
                launch_paths = yaml_index_by_install_dir[current_dir]["launch"]
                sorted_paths = sort_launch_paths(launch_paths)
                
                for relative_path in sorted_paths:
                    relative_path = relative_path.replace("<base>/", "")
                    exe_path = select_best_path(relative_path, current_path)
                    
                    if exe_path:
                        current_entry = yaml_index_by_install_dir[current_dir]
                        result[root_folder] = {
                            "exe_path": exe_path,
                            "game_name": current_entry["game_name"],
                            "steam_id": current_entry["steam_id"],
                            "lutris_id": current_entry["lutris_id"],
                            "gog_id": current_entry["gog_id"],
                            "files": current_entry["files"]
                        }
                        return result
                
            stack.append((current_path, depth, False))
            for dir_name in reversed(contents['dirs']):
                stack.append((os.path.join(current_path, dir_name), depth + 1, True))
    
    return result

class GameMatcher:
    def __init__(self, sync_folder: str = DEFAULT_SYNC_FOLDER, xml_file: str = XML_FILE, 
                yaml_file: str = YAML_FILE, indexes: dict = None, max_depth: int = 7):
        self.sync_folder = sync_folder
        self.xml_file = xml_file
        self.yaml_file = yaml_file
        self.index_dir = INDEX_DIR
        self.matches: Dict[str, Dict] = {}
        self.dir_cache = DirectoryCache()
        self.first_load_attempt = True
        self.max_depth = max_depth
        
        self.index_files = {
            'xml': os.path.join(self.index_dir, "xml_index.json"),
            'yaml': os.path.join(self.index_dir, "yaml_index.json")
        }
        
        self.indexes = self._load_indexes(indexes)
    
    def _load_indexes(self, indexes=None) -> Dict[str, Any]:
        if indexes is None:
            indexes = {
                'xml': load_index_from_file(self.index_files['xml']),
                'yaml': load_index_from_file(self.index_files['yaml'])
            }
        else:
            indexes = {
                'xml': indexes.get('xml', load_index_from_file(self.index_files['xml'])),
                'yaml': indexes.get('yaml', load_index_from_file(self.index_files['yaml']))
            }
        
        if not all(indexes.values()):
            if self.first_load_attempt:
                self.first_load_attempt = False
                logger.info("Generating indexes...")
                create_or_update_indexes()
                return self._load_indexes()
            else:
                logger.error("Could not load indexes. Execution aborted.")
                sys.exit(1)

        if indexes['yaml']:
            yaml_data = indexes['yaml']
            indexes['yaml_by_exe'] = {exe: yaml_data["_metadata"][idx] 
                                    for exe, idx in yaml_data["by_exe"].items()}
            indexes['yaml_by_path'] = {path: yaml_data["_metadata"][idx] 
                                    for path, idx in yaml_data["by_path"].items()}
            indexes['yaml_by_install_dir'] = {
                install_dir: {
                    **yaml_data["_metadata"][data["_meta"]],
                    "launch": data["launch"]
                }
                for install_dir, data in yaml_data["by_install_dir"].items()
            }
            indexes['yaml_by_gog_id'] = {gog_id: yaml_data["_metadata"][idx]
                                    for gog_id, idx in yaml_data["by_gog_id"].items()}
            indexes['yaml_by_steam_id'] = {steam_id: yaml_data["_metadata"][idx]
                                        for steam_id, idx in yaml_data["by_steam_id"].items()}
            
            indexes['yaml_by_name'] = {name: yaml_data["_metadata"][idx]
                                    for name, idx in yaml_data["by_name"].items()}
            
            indexes['yaml_by_name_fuzzy'] = {}
            for part, idx_list in yaml_data["by_name_fuzzy"].items():
                unique_indexes = list(dict.fromkeys(idx_list))
                indexes['yaml_by_name_fuzzy'][part] = [
                    yaml_data["_metadata"][idx] for idx in unique_indexes
                ]
        
        return indexes

    def _get_directory_contents(self, path: str, depth: int = 0) -> Dict[str, List[str]]:
        cached_contents = None
        try:
            cached_contents = self.dir_cache.get_directory_contents(path)
        except Exception as e:
            logger.warning(f"Warning: Cache error for {path} - {str(e)}")

        if cached_contents:
            return cached_contents
        
        try:
            contents = {'dirs': [], 'files': []}
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_dir():
                        contents['dirs'].append(entry.name)
                    else:
                        contents['files'].append(entry.name)
            
            try:
                self.dir_cache.update_directory_contents(path, contents)
            except Exception as e:
                logger.warning(f"Warning: Cache update failed for {path} - {str(e)}")
            
            return contents
            
        except Exception as e:
            logger.error(f"Error scanning directory {path}: {str(e)}")
            return {'dirs': [], 'files': []}

    def _explore_directory_tree(self, root_path: str) -> List[Dict]:
        results = []
        queue = deque([(root_path, 0)])
        
        while queue:
            current_path, depth = queue.popleft()
            
            if self.max_depth is not None and depth > self.max_depth:
                continue
                
            try:
                contents = self.dir_cache.get_directory_contents(current_path)
            except Exception:
                contents = self._get_directory_contents(current_path) 
                
            for file in contents['files']:
                results.append({
                    'path': os.path.join(current_path, file),
                    'depth': depth,
                    'type': 'file'
                })
                
            for dir_name in contents['dirs']:
                if dir_name.lower() not in IGNORED_DIRS:
                    dir_path = os.path.join(current_path, dir_name)
                    queue.append((dir_path, depth + 1))
        
        return results

    def _load_user_selected_games(self) -> Dict[str, Dict]:
        games_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "games.json")
        user_selected = {}
        
        if os.path.exists(games_json_path):
            try:
                with open(games_json_path, 'r', encoding='utf-8') as f:
                    games_data = json.load(f)
                    user_selected = {
                        folder: data for folder, data in games_data.items() 
                        if data.get('user_selected') is True
                    }
            except Exception as e:
                logger.error(f"Error loading games.json: {str(e)}")
        
        return user_selected

    def _get_excluded_folders(self, user_selected_games: Dict[str, Dict]) -> Set[str]:
        excluded = set()
        sync_folder_normalized = os.path.normcase(os.path.normpath(self.sync_folder))
        
        for folder, data in user_selected_games.items():
            if 'exe_path' in data:
                exe_path = os.path.normcase(os.path.normpath(data['exe_path']))
                if exe_path.startswith(sync_folder_normalized):
                    rel_path = os.path.relpath(os.path.dirname(exe_path), sync_folder_normalized)
                    if os.sep not in rel_path:
                        continue
                    top_subfolder = rel_path.split(os.sep)[0]
                    excluded.add(top_subfolder.lower())
        
        return excluded

    def associate_exes_with_ids(self) -> Dict[str, Dict]:
        if not os.path.exists(self.sync_folder):
            logger.error(f"Game directory '{self.sync_folder}' does not exist or cannot be accessed.")
            return {}

        user_selected_games = self._load_user_selected_games()
        excluded_folders = self._get_excluded_folders(user_selected_games)
        excluded_folders.update(IGNORED_DIRS)
        logger.info("Searching for matches in root directories...")
        self.matches = find_root_directory(
            sync_folder=self.sync_folder,
            yaml_index_by_install_dir=self.indexes['yaml_by_install_dir'],
            dir_cache=self.dir_cache,
            excluded_folders=excluded_folders
        )
        self.matches.update(user_selected_games)
        logger.info(f"Initial matches found: {len(self.matches)}")

        folders_to_process = [
            (root_folder, os.path.join(self.sync_folder, root_folder))
            for root_folder in os.listdir(self.sync_folder)
            if os.path.isdir(os.path.join(self.sync_folder, root_folder))
            and (root_folder not in self.matches) and
            (root_folder.lower() not in excluded_folders)
        ]

        logger.info("\nSearching for platform identifiers (Steam/GOG)...")
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(self._process_platform_identifiers, folder, path): folder
                for folder, path in folders_to_process
            }

            for future in as_completed(futures):
                folder = futures[future]
                try:
                    result = future.result()
                    if result:
                        self.matches[folder] = result
                        folders_to_process = [
                            (f, p) for f, p in folders_to_process 
                            if f not in self.matches
                        ]
                except Exception as e:
                    logger.error(f"Error processing {folder}: {str(e)}")

        logger.info(f"Matches after platform search: {len(self.matches)}")

        logger.info("\nSearching for matches in XML/YAML...")
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(self._process_root_folder, folder, path): folder
                for folder, path in folders_to_process
                if folder not in self.matches
            }

            for future in as_completed(futures):
                folder = futures[future]
                try:
                    result = future.result()
                    if result:
                        self.matches[folder] = result
                except Exception as e:
                    logger.error(f"Error processing {folder}: {str(e)}")

        logger.info(f"Final matches found: {len(self.matches)}")
        return self.matches

    def _process_platform_identifiers(self, root_folder: str, root_folder_path: str) -> Optional[Dict]:
        platform_info = self._identify_platform(root_folder_path)
        
        if not platform_info:
            return None
        
        if platform_info['platform'] == 'gog':
            gog_data = platform_info['data']
            return self._handle_gog_match(
                root_folder=root_folder,
                root_folder_path=root_folder_path,
                gog_info={
                    'id': gog_data['id'],
                    'name': gog_data['name'],
                    'path': gog_data['path']
                },
                exe_path=gog_data.get('exe_path', '')
            )
        elif platform_info['platform'] == 'steam':
            return self._handle_steam_match(
                root_folder=root_folder,
                root_folder_path=root_folder_path,
                steam_appid=platform_info['data']['appid'], 
                steam_file=platform_info['data']['source_file']
            )
        
        return None

    def _identify_platform(self, folder_path: str) -> Optional[Dict]:
        for item in self._explore_directory_tree(folder_path):
            if item['type'] != 'file':
                continue
                
            file_path = item['path']
            file = os.path.basename(file_path)
            file_lower = file.lower()
            
            if file_lower.startswith("goggame-") and file_lower.endswith(".info"):
                platform_info = self._handle_gog_detection(file_path, file)
                if platform_info:
                    return platform_info
            
            elif file_lower == "steam_appid.txt":
                platform_info = self._handle_steam_appid_detection(file_path)
                if platform_info:
                    return platform_info
            
            elif file_lower.endswith(('.ini', '.txt', '.cfg', '.json')):
                platform_info = self._handle_steam_pattern_detection(file_path)
                if platform_info:
                    return platform_info
        
        return None

    def _handle_gog_detection(self, file_path: str, filename: str) -> Optional[Dict]:
        try:
            data = self._load_gog_info_file(file_path)
            if not data or not all(key in data for key in ['gameId', 'rootGameId', 'name']):
                return None

            if data['gameId'] != data['rootGameId']:
                base_file = os.path.join(os.path.dirname(file_path), f"goggame-{data['rootGameId']}.info")
                if os.path.exists(base_file):
                    return self._handle_gog_detection(base_file, f"goggame-{data['rootGameId']}.info")
                return None  

            exe_path = ""
            primary_task = next((t for t in data.get('playTasks', []) if t.get('isPrimary', False)), None)
            if primary_task and 'path' in primary_task:
                exe_candidate = os.path.abspath(os.path.join(os.path.dirname(file_path), primary_task['path']))
                if os.path.exists(exe_candidate):
                    exe_path = exe_candidate

            return {
                'platform': 'gog',
                'data': {
                    'id': data['gameId'],
                    'name': str(data['name']),
                    'path': os.path.abspath(file_path),
                    'exe_path': exe_path
                }
            }

        except Exception as e:
            logger.error(f"Error processing {file_path}: {str(e)}")
            return None

    def _load_gog_info_file(self, file_path: str) -> Optional[Dict]:
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return json.load(f)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        return None

    def _handle_steam_appid_detection(self, file_path: str) -> Optional[Dict]:
        try:
            with open(file_path, 'r') as f:
                appid = f.read().strip()
                if appid.isdigit():
                    return {
                        'platform': 'steam',
                        'data': {
                            'appid': appid,
                            'source_file': file_path
                        }
                    }
        except (IOError, UnicodeDecodeError) as e:
            logger.error(f"Error reading {file_path}: {str(e)}")
        return None

    def _handle_steam_pattern_detection(self, file_path: str) -> Optional[Dict]:
        patterns = [
            re.compile(r'appid\s*=\s*(\d{3,})', re.IGNORECASE),  # Original pattern
            re.compile(r'#\s*appid\s*[\r\n]+\s*id\s*=\s*(\d{3,})', re.IGNORECASE)  # New pattern
        ]
        
        try:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
            
            if file_path.lower().endswith('.json'):
                try:
                    json_data = json.loads(content)
                    if appid := self._find_appid_in_json(json_data):
                        return self._build_steam_response(appid, file_path)
                except json.JSONDecodeError:
                    pass  
            
            for pattern in patterns:
                if match := pattern.search(content):
                    return self._build_steam_response(match.group(1), file_path)
                    
        except Exception as e:
            logger.error(f"Error processing {file_path}: {str(e)}")
        
        return None

    def _build_steam_response(self, appid: str, source_file: str) -> Dict:
        return {
            'platform': 'steam',
            'data': {
                'appid': appid,
                'source_file': source_file
            }
        }

    def _search_appid_in_file(self, file_path: str, pattern: re.Pattern) -> Optional[str]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                if file_path.lower().endswith('.json'):
                    try:
                        json_data = json.loads(content)
                        return self._find_appid_in_json(json_data)
                    except json.JSONDecodeError:
                        pass
                
                match = pattern.search(content)
                if match:
                    return match.group(1)
                    
        except (IOError, UnicodeDecodeError) as e:
            logger.error(f"Error reading {file_path}: {str(e)}")
        
        return None

    def _find_appid_in_json(self, json_data: Any) -> Optional[str]:
        try:
            if isinstance(json_data, dict):
                if 'appid' in json_data:
                    appid = json_data['appid']
                    if isinstance(appid, (str, int, float)):
                        appid_str = str(int(float(appid))) 
                        if len(appid_str) >= 3:
                            return appid_str
                
                for value in json_data.values():
                    if result := self._find_appid_in_json(value):
                        return result
            
            elif isinstance(json_data, list):
                for item in json_data:
                    if result := self._find_appid_in_json(item):
                        return result
        
        except (TypeError, ValueError) as e:
            logger.error(f"Error processing JSON: {str(e)}")
        
        return None

    def _handle_steam_match(self, root_folder: str, root_folder_path: str, 
                        steam_appid: str, steam_file: str) -> Optional[Dict]:
        yaml_entry = self.indexes['yaml_by_steam_id'].get(steam_appid)
        
        result = {
            "exe_path": "",
            "game_name": os.path.basename(root_folder_path),
            "steam_id": steam_appid,
            "lutris_id": "",
            "gog_id": ""
        }
        
        exe_path = None
        
        if yaml_entry:
            result.update({
                "game_name": yaml_entry.get("game_name", result["game_name"]),
                "lutris_id": yaml_entry.get("lutris_id", ""),
                "gog_id": yaml_entry.get("gog_id", ""),
                "files": yaml_entry.get("files", {})
            })
            
            if "launch" in yaml_entry: 
                launch_paths = yaml_entry["launch"]
                sorted_paths = sort_launch_paths(launch_paths)
                
                for relative_path in sorted_paths:
                    relative_path = relative_path.replace("<base>/", "")
                    exe_path = select_best_path(relative_path, root_folder_path)
                    if exe_path:
                        break
        
        if not exe_path:
            exe_path = self._find_best_exe_in_folder(
                root_folder_path, 
                reference_name=result["game_name"],
                search_subdirs=True
            )
        
        if exe_path:
            result["exe_path"] = exe_path
            return result
        
        return None 

    def _handle_gog_match(self, root_folder: str, root_folder_path: str, 
                        gog_info: Dict, exe_path: str = '') -> Optional[Dict]:
        yaml_entry = self.indexes['yaml_by_gog_id'].get(gog_info['id'])
        
        result = {
            "exe_path": exe_path, 
            "game_name": gog_info['name'],
            "steam_id": "",
            "lutris_id": "",
            "gog_id": gog_info['id']
        }
        
        if yaml_entry:
            result.update({
                "game_name": yaml_entry.get("game_name", result["game_name"]),
                "steam_id": yaml_entry.get("steam_id", ""),
                "lutris_id": yaml_entry.get("lutris_id", ""),
                "files": yaml_entry.get("files", {})
            })
            
            if not result["exe_path"] and "launch" in yaml_entry:
                for relative_path in sort_launch_paths(yaml_entry["launch"]):
                    candidate = select_best_path(relative_path.replace("<base>/", ""), root_folder_path)
                    if candidate:
                        result["exe_path"] = candidate
                        break
        
        if not result["exe_path"]:
            result["exe_path"] = self._find_best_exe_in_folder(
                root_folder_path,
                reference_name=result["game_name"],
                search_subdirs=False
            )
        
        return result if result["exe_path"] else None

    def _find_best_exe_in_folder(self, folder_path: str, reference_name: str, 
                            search_subdirs: bool = False) -> Optional[str]:
        best_exe = None
        best_score = -1
        
        items_to_search = (
            self._explore_directory_tree(folder_path) 
            if search_subdirs 
            else [{'path': folder_path, 'type': 'directory', 'depth': 0}]
        )
        
        for item in items_to_search:
            if item['type'] == 'directory' and not search_subdirs:
                contents = self._get_directory_contents(item['path'])
                files = contents['files']
            elif item['type'] == 'file':
                files = [os.path.basename(item['path'])]
            else:
                continue
                
            for file in files:
                if not file.lower().endswith('.exe') or file.lower() in IGNORED_FILES:
                    continue
                    
                file_path = (
                    os.path.join(item['path'], file) 
                    if item['type'] == 'directory' 
                    else item['path']
                )
                
                current_score = self._calculate_name_similarity(
                    os.path.splitext(file)[0],
                    reference_name
                )
                
                if current_score > best_score:
                    best_score = current_score
                    best_exe = file_path
        
        return best_exe

    def _calculate_name_similarity(self, name1: str, name2: str) -> int:
        name1 = name1.lower()
        name2 = name2.lower()
        
        if name1 in name2 or name2 in name1:
            return max(len(name1), len(name2))
        
        common_prefix = 0
        for a, b in zip(name1, name2):
            if a == b:
                common_prefix += 1
            else:
                break
        
        return common_prefix

    def _process_root_folder(self, root_folder: str, root_folder_path: str) -> Dict:
        try:
            jre_paths = self._find_jre_paths(root_folder_path)
            xml_candidates = self._find_xml_candidates(root_folder_path)
            
            if xml_candidates:
                best_match = self._find_best_match_from_candidates(xml_candidates)
            else:
                best_match = self._find_direct_yaml_match(root_folder_path)
            
            if not best_match and (jre_paths['jre'] or jre_paths['jre_x64']):
                best_match = self._find_java_match(jre_paths)
            
            if not best_match:
                best_match = self._find_exe_and_match_by_name(root_folder_path)

            return best_match
        
        except Exception as e:
            logger.error(f"Error processing {root_folder}: {str(e)}")
            return None
    
    def _find_jre_paths(self, root_folder_path: str) -> Dict[str, Optional[str]]:
        jre_paths = {'jre': None, 'jre_x64': None}
        
        for item in self._explore_directory_tree(root_folder_path):
            if item['type'] != 'directory':
                continue
                
            dir_name = os.path.basename(item['path'])
            if dir_name == 'jre':
                jre_paths['jre'] = item['path']
            elif dir_name == 'jre_x64':
                jre_paths['jre_x64'] = item['path']
        
        return jre_paths
    
    def _find_xml_candidates(self, root_folder_path: str) -> List[Dict]:
        candidates = []
        
        for item in self._explore_directory_tree(root_folder_path):
            if item['type'] != 'file':
                continue
                
            file = os.path.basename(item['path'])
            if not file.lower().endswith('.exe'):
                continue
                
            exe_name_without_ext = os.path.splitext(file)[0].lower()
            if exe_name_without_ext in IGNORED_FILES:
                continue
                
            exe_path = normalize_path(item['path'])
            relative_path = normalize_path(os.path.relpath(exe_path, self.sync_folder))
            
            if game_name := self.indexes['xml'].get(exe_name_without_ext):
                candidates.append({
                    "exe_path": exe_path,
                    "game_name": game_name,
                    "relative_path": relative_path,
                    "depth": item['depth']
                })
        
        return candidates
    
    def _find_best_match_from_candidates(self, candidates: List[Dict]) -> Optional[Dict]:
        best_match = None
        best_match_score = 0
        
        for candidate in candidates:
            yaml_entry = (self.indexes['yaml_by_path'].get(candidate["relative_path"]) or 
                        self.indexes['yaml_by_exe'].get(os.path.basename(candidate["exe_path"]).lower()))
            
            game_info = {
                "exe_path": candidate["exe_path"],
                "game_name": yaml_entry["game_name"] if yaml_entry else candidate["game_name"],
                "steam_id": yaml_entry["steam_id"] if yaml_entry else None,
                "lutris_id": yaml_entry["lutris_id"] if yaml_entry else None,
                "gog_id": yaml_entry["gog_id"] if yaml_entry else None,
                "files": yaml_entry["files"] if yaml_entry else {}
            }
            
            match_score = len(candidate["relative_path"])
            if match_score > best_match_score:
                best_match = game_info
                best_match_score = match_score
        
        return best_match
    
    def _find_direct_yaml_match(self, root_folder_path: str) -> Optional[Dict]:
        best_match = None
        best_match_score = 0
        
        for item in self._explore_directory_tree(root_folder_path):
            if item['type'] != 'file':
                continue
                
            file = os.path.basename(item['path'])
            if not file.lower().endswith('.exe'):
                continue
                
            exe_name_without_ext = os.path.splitext(file)[0].lower()
            if exe_name_without_ext in IGNORED_FILES:
                continue
                
            exe_path = normalize_path(item['path'])
            relative_path = normalize_path(os.path.relpath(exe_path, self.sync_folder))
            
            yaml_entry = (self.indexes['yaml_by_path'].get(relative_path) or 
                        self.indexes['yaml_by_exe'].get(file.lower()))
            
            if not yaml_entry:
                continue
            
            game_info = {
                "exe_path": exe_path,
                "game_name": yaml_entry["game_name"],
                "steam_id": yaml_entry["steam_id"],
                "lutris_id": yaml_entry["lutris_id"],
                "gog_id": yaml_entry["gog_id"],
                "depth": item['depth'],
                "files": yaml_entry["files"]
            }
            
            match_score = 1000 - item['depth']  
            if match_score > best_match_score:
                best_match = game_info
                best_match_score = match_score
        
        return best_match
    
    def _find_java_match(self, jre_paths: Dict[str, Optional[str]]) -> Optional[Dict]:
        best_match = None
        best_match_score = 0
        
        search_order = ['jre_x64', 'jre'] if is_64bit_system() else ['jre', 'jre_x64']
        
        for jre_type in search_order:
            if not jre_paths[jre_type]:
                continue
            
            for java_exe in ["javaw.exe", "java.exe"]:
                java_path = os.path.join(jre_paths[jre_type], "bin", java_exe)
                if not os.path.exists(java_path):
                    continue
                
                relative_path = normalize_path(os.path.relpath(java_path, self.sync_folder))
                
                yaml_entry = (self.indexes['yaml_by_path'].get(relative_path) or 
                            self.indexes['yaml_by_exe'].get(os.path.basename(java_path).lower()))
                
                if not yaml_entry:
                    continue
                
                game_info = {
                    "exe_path": java_path,
                    "game_name": yaml_entry["game_name"],
                    "steam_id": yaml_entry["steam_id"],
                    "lutris_id": yaml_entry["lutris_id"],
                    "gog_id": yaml_entry["gog_id"],
                    "files": yaml_entry["files"]
                }
                
                match_score = len(relative_path)
                if match_score > best_match_score:
                    best_match = game_info
                    best_match_score = match_score
        
        return best_match
    
    def _find_exe_and_match_by_name(self, root_folder_path: str) -> Optional[Dict]:
        exe_files = []
        folder_name = os.path.basename(root_folder_path)
        
        for item in self._explore_directory_tree(root_folder_path):
            if item['type'] != 'file':
                continue
                
            file = os.path.basename(item['path'])
            if not file.lower().endswith('.exe') or file.lower() in IGNORED_FILES:
                continue
                
            exe_files.append({
                'path': item['path'],
                'name': os.path.splitext(file)[0],
                'name_lower': os.path.splitext(file)[0].lower(),
                'relative_path': normalize_path(os.path.relpath(item['path'], self.sync_folder))
            })
        
        if not exe_files:
            return None

        for exe in exe_files:
            if match := self.indexes['yaml_by_path'].get(exe['relative_path'].lower()):
                return self._format_match(exe['path'], match)
            
            if match := self.indexes['yaml_by_exe'].get(os.path.basename(exe['path']).lower()):
                return self._format_match(exe['path'], match)
            
            if match := self.indexes['yaml_by_name'].get(exe['name_lower']):
                return self._format_match(exe['path'], match)
        
        if exe_files:
            def _simple_match_score(a: str, b: str) -> int:
                a, b = a.lower(), b.lower()
                if a == b:
                    return 100
                if a in b or b in a:
                    return 90
                common = set(a.split()) & set(b.split())
                return int(80 * len(common) / max(len(a.split()), len(b.split())))

            best_match = None
            best_score = 0
            
            search_terms = {folder_name.lower()}
            for exe in exe_files:
                search_terms.add(exe['name_lower'])
                search_terms.update(exe['name_lower'].split())
            
            for term in search_terms:
                if term in self.indexes['yaml_by_name_fuzzy']:
                    for match in self.indexes['yaml_by_name_fuzzy'][term]:
                        current_score = _simple_match_score(term, match['game_name'])
                        if current_score > best_score:
                            best_score = current_score
                            best_match = match
                            if best_score == 100:  
                                return self._format_match(exe_files[0]['path'], best_match)
            
            if best_match and best_score >= 50: 
                return self._format_match(exe_files[0]['path'], best_match)
        
        best_exe = max(exe_files, key=lambda x: len(x['name'])) 
        return {
            "exe_path": best_exe['path'],
            "game_name": folder_name,
            "steam_id": "",
            "lutris_id": "",
            "gog_id": "",
            "files": {}
        }

    def _format_match(self, exe_path: str, yaml_data: dict) -> Dict:
        return {
            "exe_path": exe_path,
            "game_name": yaml_data.get("game_name", os.path.basename(exe_path)),
            "steam_id": yaml_data.get("steam_id", ""),
            "lutris_id": yaml_data.get("lutris_id", ""),
            "gog_id": yaml_data.get("gog_id", ""),
            "files": yaml_data.get("files", {})
        }

def associate_exes_with_ids(sync_folder: str = DEFAULT_SYNC_FOLDER, xml_file: str = XML_FILE, 
                            yaml_file: str = YAML_FILE, indexes: dict = None
                            , max_depth: int = 7) -> Dict[str, Dict]:

    games_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "games.json")
    user_selected_games = {}
    
    if os.path.exists(games_json_path):
        try:
            with open(games_json_path, 'r', encoding='utf-8') as f:
                games_data = json.load(f)
                user_selected_games = {
                    folder: data for folder, data in games_data.items() 
                    if data.get('user_selected') is True
                }
        except Exception as e:
            logger.error(f"Error loading games.json: {str(e)}")
    
    matcher = GameMatcher(sync_folder, xml_file, yaml_file, indexes, max_depth)
    all_matches = matcher.associate_exes_with_ids()
    
    final_matches = {}
    
    for folder, data in all_matches.items():
        if folder not in user_selected_games:
            final_matches[folder] = data
    
    final_matches.update(user_selected_games)
    
    return final_matches

def create_or_update_indexes() -> Dict[str, Any]:
    index_dir = INDEX_DIR
    os.makedirs(index_dir, exist_ok=True)

    indexes = {}

    with ThreadPoolExecutor(max_workers=2) as executor:
        xml_future = executor.submit(download_file, XML_URL, XML_FILE)
        yaml_future = executor.submit(download_file, YAML_URL, YAML_FILE)
        xml_changed = xml_future.result()
        yaml_changed = yaml_future.result()

    with ThreadPoolExecutor() as executor:
        futures = {}
        if xml_changed or not os.path.exists(os.path.join(index_dir, "xml_index.json")):
            futures['xml'] = executor.submit(
                lambda: index_xml_data(ET.parse(XML_FILE).getroot()))
        
        if yaml_changed or not os.path.exists(os.path.join(index_dir, "yaml_index.json")):
            futures['yaml'] = executor.submit(
                lambda: index_yaml_data(load_yaml_file(YAML_FILE)))

        for index_type, future in futures.items():
            try:
                indexes[index_type] = future.result()
                save_index_to_file(
                    indexes[index_type],
                    os.path.join(index_dir, f"{index_type}_index.json"))
            except Exception as e:
                logger.error(f"Error: {str(e)[:100]}")

    logger.info("Índices actualizados")
    return indexes

def verify_and_download_files():

    if not os.path.exists(XML_FILE):
        logger.info(f"XML file not found in path: {XML_FILE}")
        logger.info("trying to download the XML file from GitHub...")
        if not download_file(XML_URL, XML_FILE):
            logger.error("Not able to download the XML file.")

    if not os.path.exists(YAML_FILE):
        logger.info(f"YAML file not found in path: {YAML_FILE}")
        logger.info("trying to download the YAML file from GitHub...")
        if not download_file(YAML_URL, YAML_FILE):
            logger.error("not able to download the YAML file.")

    return create_or_update_indexes()


def get_sync_folders() -> List[str]:

    if not os.path.exists(SYNC_FOLDERS_FILE):
        default_folders = get_default_sync_folders()
        try:
            with open(SYNC_FOLDERS_FILE, 'w', encoding='utf-8') as f:
                f.write("\n".join(default_folders))
            return [folder for folder in default_folders if os.path.exists(folder)]
        except Exception as e:
            logger.error(f"Couldn't create {SYNC_FOLDERS_FILE}: {e}")
            return [DEFAULT_SYNC_FOLDER]

    try:
        with open(SYNC_FOLDERS_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
        if not content: 
            default_folders = get_default_sync_folders()
            try:
                with open(SYNC_FOLDERS_FILE, 'w', encoding='utf-8') as f:
                    f.write("\n".join(default_folders))
                return [folder for folder in default_folders if os.path.exists(folder)]
            except Exception as e:
                logger.error(f"Couldn't update {SYNC_FOLDERS_FILE}: {e}")
                return [DEFAULT_SYNC_FOLDER]
    except Exception as e:
        logger.error(f"Error reading {SYNC_FOLDERS_FILE}: {e}")
        return [DEFAULT_SYNC_FOLDER]

    try:
        with open(SYNC_FOLDERS_FILE, 'r', encoding='utf-8') as f:
            folders = [line.strip() for line in f if line.strip()]
            
        valid_folders = [f for f in folders if os.path.exists(f)]
        
        return valid_folders if valid_folders else [DEFAULT_SYNC_FOLDER]
        
    except Exception as e:
        logger.error(f"Error processing {SYNC_FOLDERS_FILE}: {e}")
        return [DEFAULT_SYNC_FOLDER]


def get_default_sync_folders() -> List[str]:
    default_folders = set()
    
    home_games = os.path.join(Path.home(), "Games")
    default_folders.add(home_games)

    '''It's possible to rely on configuration files to directly obtain
the specific installation directories for each game for store installations.
The problem is that, in the case of GOG (which is the one I've been able to test; I assume Epic is the same), we have to rely on the installation folder name being exactly the name of the game and then search for the .exe file for that game. It's not a bad solution and could improve efficiency. However, our current logic is perfectly capable of
handling game searches, especially for GOG, and with the addition of manual search, it seems like a complete
waste of time. However, if you decide to adopt this approach,
for sideloads, the location is: <heroic-path>/sideloads_apps/library.json (it contains relevant information, but since it is a sideload, our application already manages it and can generate duplicates) (app_name is related to the file of the same name in
<heroic-path>/GamesConfig/<app_name>, which contains the Wine prefix (for games) and other relevant information)
For GOG: <heroic-path>/gog_store/installed.json (little relevant information, although we have tools to manage it)
    '''
    
    for path in HEROIC_PATHS:
        if os.path.exists(path):
            if path.endswith(".json"):
                try:
                    with open(path, 'r') as f:
                        config = json.load(f)
                        if "defaultInstallPath" in config:
                            default_folders.add(config["defaultInstallPath"])
                except:
                    continue
    if any(os.path.exists(path) for path in HEROIC_PATHS) and len(default_folders) == 1:
        default_folders.add(os.path.join(Path.home(), "Games", "Heroic"))

    # 3. GOG Galaxy (Untested)
    if os.name == 'nt': 
        
        for path in GOG_PATHS:
            if os.path.exists(path):
                if path.endswith(".json"):
                    try:
                        with open(path, 'r') as f:
                            config = json.load(f)
                            if "libraryPath" in config:
                                default_folders.add(config["libraryPath"])
                    except:
                        continue
                else:
                    default_folders.add(os.path.join(Path.home(), "GOG Games"))
    
    if not default_folders:
        default_folders.add(DEFAULT_SYNC_FOLDER)
    
    return default_folders

def run_identification():
    indexes = verify_and_download_files()
    sync_folders = get_sync_folders()
    max_depth = 8
    
    all_matches = {}
    for folder in sync_folders:
        logger.info(f"\n Processing folder: {folder}")
        matches = associate_exes_with_ids(folder, XML_FILE, YAML_FILE, indexes, max_depth)
        all_matches.update(matches)
    
    return all_matches

def add_files_to_user_selected(games_data: dict, matcher: GameMatcher) -> dict:
    yaml_by_name = matcher.indexes.get('yaml_by_name', {})
    
    for game_name, game_info in games_data.items():
        if game_info.get('user_selected') and 'files' not in game_info:
            yaml_entry = yaml_by_name.get(game_info['name'].lower())
            if yaml_entry:
                game_info['files'] = yaml_entry.get('files', {})
    
    return games_data

def main():

    start_time = time.perf_counter()
    
    logger.info("Starting Game identification process...")
    matches = run_identification()

    logger.info("\nResults:")
    for folder, data in matches.items():
        logger.info(f"\nFolder: {folder}")
        logger.info(f"  EXE found: {data['exe_path']}")
        logger.info(f"  Game: {data['game_name']}")
        if data['steam_id']:
            logger.info(f"  SteamID: {data['steam_id']}")
        if data['lutris_id']:
            logger.info(f"  LutrisID: {data['lutris_id']}")
        if data['gog_id']:
            logger.info(f"  GOGID: {data['gog_id']}")
    
    end_time = time.perf_counter()
    elapsed = end_time - start_time
    
    if elapsed > 60:
        minutes = int(elapsed // 60)
        seconds = elapsed % 60
        time_str = f"{minutes} minutes y {seconds:.2f} seconds"
    else:
        time_str = f"{elapsed:.2f} seconds"
    
    logger.info(f"\nFinished. Total time: {time_str}")

if __name__ == "__main__":
    main()
