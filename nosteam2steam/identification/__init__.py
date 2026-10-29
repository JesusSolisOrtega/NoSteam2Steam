"""Game identification and metadata subsystem."""

from nosteam2steam.identification.candidates import CandidateResolver
from nosteam2steam.identification.data_manager import (
    GameDataManager,
    get_excluded_folders,
    load_user_selected_games,
)
from nosteam2steam.identification.heuristics import (
    calculate_name_similarity,
    clean_executable_name,
    find_best_exe_in_folder,
    simple_match_score,
)
from nosteam2steam.identification.identifier import (
    GameMatcher,
    add_files_to_user_selected,
    associate_exes_with_ids,
    run_identification,
)
from nosteam2steam.identification.lutris import (
    LutrisDataEnhancer,
    format_lutris_game_data,
    search_lutris_games,
)
from nosteam2steam.identification.manifests import (
    ManifestRepository,
    create_or_update_indexes,
    download_file,
    verify_and_download_files,
)
from nosteam2steam.identification.manual_adder import manual_add_game
from nosteam2steam.identification.platform import PlatformDetector, PlatformResolver
from nosteam2steam.identification.folders import (
    get_default_sync_folders,
    get_sync_folders,
)
from nosteam2steam.identification.paths import (
    is_64bit_system,
    is_steamos,
    normalize_path,
    select_best_path,
    sort_launch_paths,
    supports_vulkan,
)
from nosteam2steam.identification.scanner import (
    DirectoryCache,
    explore_directory_tree,
    find_root_directory,
)

__all__ = [
    "CandidateResolver",
    "DirectoryCache",
    "GameDataManager",
    "GameMatcher",
    "LutrisDataEnhancer",
    "ManifestRepository",
    "PlatformDetector",
    "PlatformResolver",
    "add_files_to_user_selected",
    "associate_exes_with_ids",
    "calculate_name_similarity",
    "clean_executable_name",
    "create_or_update_indexes",
    "download_file",
    "explore_directory_tree",
    "find_best_exe_in_folder",
    "find_root_directory",
    "format_lutris_game_data",
    "get_default_sync_folders",
    "get_excluded_folders",
    "get_sync_folders",
    "is_64bit_system",
    "is_steamos",
    "load_user_selected_games",
    "manual_add_game",
    "normalize_path",
    "run_identification",
    "search_lutris_games",
    "select_best_path",
    "simple_match_score",
    "sort_launch_paths",
    "supports_vulkan",
    "verify_and_download_files",
]
