import re
from pathlib import Path
import logging
from config import get_current_user

from config import COMPATDATA_PATH, ROOT_PATH

logger = logging.getLogger('GBM_Backup')

class PathConverter:
    CONVERSION_MAP = {
        # Windows (Proton)
        '<winAppData>': ('users/steamuser/AppData/Roaming', '%APPDATA%'),
        '<winLocalAppData>': ('users/steamuser/AppData/Local', '%LOCALAPPDATA%'),
        '<winLocalAppDataLow>': ('users/steamuser/AppData/LocalLow', '%USERPROFILE%\\AppData\\LocalLow'),
        '<winDocuments>': ('users/steamuser/Documents', '%USERDOCUMENTS%'),
        '<winPublic>': ('users/Public', '%PUBLIC%'),
        '<winProgramData>': ('users/Public', '%PROGRAMDATA%'),
        '<winDir>': ('windows', '%WINDIR%'),
        
        # Linux (Native)
        '<xdgData>': ('.local/share', '$XDG_DATA_HOME'),
        '<xdgConfig>': ('.config', '$XDG_CONFIG_HOME'),
    }

    # Extensions that identify a Windows executable
    WINDOWS_EXECUTABLE_EXTS = {'.exe', '.dll', '.bat', '.cmd'}

    @staticmethod
    def _is_windows_game(game_data):
        exe_path = game_data.get("exe_path")
        if not exe_path:
            return False
        return Path(exe_path).suffix.lower() in PathConverter.WINDOWS_EXECUTABLE_EXTS

    @staticmethod
    def _should_process_path(path_info, tags, game_data=None):
        if not tags:
            return True
            
        tags_set = set(tags)
        has_save = 'save' in tags_set
        only_config = tags_set == {'config'}
        
        if not has_save and only_config:
            logger.debug(f"Filtered by tags - Configuration only: {path_info}")
            return False

        if game_data and PathConverter._is_windows_game(game_data):
            when_conditions = path_info.get('when', [])
            if when_conditions:
                has_any_os_condition = False
                has_windows_os = False
                
                for cond in when_conditions:
                    if 'os' in cond:
                        has_any_os_condition = True
                        if cond['os'].lower() == 'windows':
                            has_windows_os = True
                            break
                
                if has_any_os_condition and not has_windows_os:
                    logger.debug(f"Filtered by OS - Not Windows: {path_info}")
                    return False

        return True

    @staticmethod
    def get_proton_path(game_id):
        if not game_id:
            logger.warning("Attempt to get Proton path without game_id")
            return None
        return COMPATDATA_PATH / str(game_id) / 'pfx' / 'drive_c'

    @staticmethod
    def expand_path(original_path, game_data=None, system='auto'):
        if not game_data:
            logger.warning("Attempt to expand path without game_data")
            return []

        game_id = game_data.get("app_id_short")
        install_dir = game_data.get("install_dir")
        exe_path = game_data.get("exe_path")

        systems = []
        if system == 'auto':
            if any(v in original_path for v in ['<win', '%APPDATA%']):
                systems.append('windows')
            if any(v in original_path for v in ['<xdg', '$XDG_']):
                systems.append('linux')
            if not systems:
                systems = ['windows', 'linux']
        else:
            systems = [system]

        results = []
        base_path = None
        for system_obj in systems:
            if system_obj == 'windows' and not game_id:
                logger.debug(f"Windows game without ID, skipping: {original_path}")
                continue

            proton_path = PathConverter.get_proton_path(game_id) if system_obj == 'windows' and game_id else None
            
            if exe_path and not base_path:
                exe_path_obj = Path(exe_path)
                for parent in exe_path_obj.parents:
                    if install_dir and parent.name == install_dir:
                        base_path = parent
                        break

            replacements = {
                '<base>': (str(base_path) if base_path else '', '<base>'),
                '<game>': (install_dir if install_dir else Path(exe_path).stem if exe_path else '', '<game>'),
                '<root>': (str(ROOT_PATH) if system_obj == 'windows' else '', str(ROOT_PATH) if system_obj == 'windows' else '<root>'),
                '<home>': (str('users/steamuser') if system_obj == 'windows' else str(Path.home()), str('%USERPROFILE%') if system_obj == 'windows' else '<home>'),
                '<storeGameId>': (str(game_id) if game_id else '', '<storeGameId>'),
                '<storeUserId>': ('<storeUserId>', '<storeUserId>'),
            }

            physical_path = original_path
            meta_path = original_path
            
            for var, (physical, meta) in {**PathConverter.CONVERSION_MAP, **replacements}.items():
                if var in physical_path:
                    physical_path = physical_path.replace(var, physical)
                    meta_path = meta_path.replace(var, meta)

            physical_path = physical_path.replace('\\', '/')
            
            try:
                if system_obj == 'windows' and proton_path:
                    if not (physical_path.startswith(str(proton_path))
                            or original_path.startswith('<base>')
                            or original_path.startswith('<root>')):
                        if physical_path.startswith('drive_c/'):
                            physical_path = physical_path[8:]
                        final_path = (proton_path / physical_path).resolve()
                    else:
                        final_path = Path(physical_path).resolve()
                else:
                    final_path = Path(physical_path).expanduser().resolve()

                if final_path:
                    results.append({
                        'physical_path': final_path,
                        'meta_path': meta_path,
                        'system': system_obj
                    })
            except Exception as e:
                logger.debug(f"Error resolving path {physical_path}: {str(e)}")

            if original_path.startswith('<base>'):
                break
        return results

    @staticmethod
    def _extract_game_name(path):
        match = re.search(r'/([^/]+)(/|$)', path)
        return match.group(1) if match else '<game>'

    @staticmethod
    def search_paths(original_path, game_data=None):
        if not game_data:
            return []
            
        file_info = game_data.get('files', {}).get(original_path, {})
        tags = file_info.get('tags', [])
        
        if not PathConverter._should_process_path(file_info, tags, game_data):
            logger.debug(f"Path filtered by conditions: {original_path}")
            return []
            
        variants = PathConverter.expand_path(original_path, game_data)
        results = []
        
        for variant in variants:
            path = variant['physical_path']
            try:
                if path.is_symlink():
                    path = path.resolve()
            except (OSError, RuntimeError) as e:
                logger.debug(f"Error resolving symlink {path}: {str(e)}")
                continue
                
            if '<storeUserId>' in str(path):
                parent = path.parent
                pattern = r'\d{3,}'
                if parent.exists():
                    for child in parent.iterdir():
                        if child.is_dir() and re.fullmatch(pattern, child.name):
                            new_path = parent / child.name / path.name
                            if new_path.exists():
                                results.append({
                                    'path': new_path,
                                    'meta': variant['meta_path'].replace('<storeUserId>', child.name),
                                    'system': variant['system']
                                })
            else:
                if '*' in str(path):
                    for match in path.parent.glob(path.name):
                        if match.exists():
                            results.append({
                                'path': match,
                                'meta': variant['meta_path'],
                                'system': variant['system']
                            })
                elif path.exists():
                    results.append({
                        'path': path,
                        'meta': variant['meta_path'],
                        'system': variant['system']
                    })
        
        logger.debug(f"Found {len(results)} variants for {original_path}")
        return results

    @staticmethod
    def process_game_entry(game_data):
        if not game_data.get('files'):
            logger.debug(f"Game {game_data.get('app_id_short', '')} has no defined paths")
            return []
        
        processed_paths = []
        
        for original_path, info in game_data.get('files', {}).items():
            if not PathConverter._should_process_path(info, info.get('tags', []), game_data):
                continue
                
            for result in PathConverter.search_paths(original_path, game_data):
                processed_paths.append({
                    'physical_path': result['path'],
                    'original_path': original_path,
                    'meta_path': result['meta'],
                    'system': result['system'],
                    'tags': info.get('tags', []),
                    'when': info.get('when', [])
                })
        if len(processed_paths) > 1:
            logger.info(f"Processed {len(processed_paths)} valid paths for {game_data.get('app_id_short', '')}")
        return processed_paths

    @staticmethod
    def search_saves_on_alternative_appids(game_data, alternative_appids):
        if not game_data or not alternative_appids:
            logger.warning("Alternative search without sufficient data")
            return []
            
        processed_paths = []
        original_appid = game_data.get('app_id_short')
        
        for alternative_appid in alternative_appids:
            modified_game = game_data.copy()
            modified_game['app_id_short'] = alternative_appid
            
            try:
                paths = PathConverter.process_game_entry(modified_game)
                for path in paths:
                    path['appid_origen'] = alternative_appid
                    path['appid_actual'] = original_appid
                processed_paths.extend(paths)
            except Exception as e:
                logger.error(f"Error processing alternative appid {alternative_appid}: {str(e)}")
                continue

            if processed_paths:
                break
        
        return processed_paths


def _expand_placeholders_to_windows(path, game_data):
    game_id = game_data.get("app_id_short")
    exe_path = game_data.get("exe_path")
    install_dir = game_data.get("install_dir")

    base_path = None
    if exe_path and ('<base>' in path or '%BASEPATH%' in path):
        exe_path_obj = Path(exe_path)
        for parent in exe_path_obj.parents:
            if install_dir and parent.name == install_dir:
                base_path = parent
                break

    store_user_id = None
    if '<storeUserId>' or '%SteamID3%' in path:
        store_user_id = get_current_user()

    placeholders = {
        '<base>': str(base_path) if base_path else '',
        '<root>': str(COMPATDATA_PATH.parent),  # ../compatdata
        '<game>': install_dir if install_dir else Path(exe_path).stem if exe_path else '',
        '<storeGameId>': str(game_id) if game_id else '',
        '<storeUserId>': str(store_user_id) if store_user_id else '*',
        '<home>': 'users/steamuser',
        '%BASEPATH%': str(base_path) if base_path else '',
        '%SteamID3%': str(store_user_id) if store_user_id else '*',
    }

    for ph, value in placeholders.items():
        path = path.replace(ph, value)

    return path


def transform_path_from_windows_to_proton(windows_path, game_data, compatdata_path=COMPATDATA_PATH):
    expanded_path = _expand_placeholders_to_windows(windows_path, game_data)

    if 'steam_app_id' in game_data:
        steam_app_id_str = str(game_data['steam_app_id'])
        app_id_short_str = str(game_data.get('app_id_short', ''))
        expanded_path = expanded_path.replace(steam_app_id_str, app_id_short_str)

    env_vars = {
        "%USERDOCUMENTS%": "users/steamuser/Documents",
        "%USERPROFILE%": "users/steamuser",
        "%APPDATA%": "users/steamuser/AppData/Roaming",
        "%LOCALAPPDATA%": "users/steamuser/AppData/Local",
        "%PROGRAMFILES%": "Program Files",
        "%PROGRAMFILES(X86)%": "Program Files (x86)",
        "%PUBLIC%": "users/Public",
        "%TEMP%": "users/steamuser/AppData/Local/Temp",
        "%COMMONDOCUMENTS%": "users/Public/Documents",
        "%Steam%": "Program Files (x86)/Steam"
    }

    for var, value in env_vars.items():
        expanded_path = expanded_path.replace(var, value)

    relative_path = Path(expanded_path.replace("\\", "/"))
    
    needs_proton = not (
        windows_path.startswith('<base>') or 
        windows_path.startswith('<root>') or
        windows_path.startswith('%BASEPATH%')
    )

    if needs_proton and game_data.get("app_id_short"):
        final_path = compatdata_path / game_data["app_id_short"] / "pfx" / "drive_c" / relative_path
    else:
        final_path = relative_path

    return final_path
