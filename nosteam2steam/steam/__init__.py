"""Steam library integration and shortcut management subsystem."""

from nosteam2steam.steam.shortcuts import (
    main,
    add_games_to_shortcuts,
    save_shortcuts,
    load_games,
)
from nosteam2steam.steam.vdf_binary import (
    load_shortcuts,
    reindex_shortcuts_alphabetically,
    get_valid_shortcuts,
)
from nosteam2steam.steam.icon_extractor import extract_icon
from nosteam2steam.steam.compat import set_proton_compat_tool, set_proton_compat_tools
from nosteam2steam.steam.ids import (
    STEAMID64_BASE,
    accountid_to_steamid64,
    generate_app_id,
    generate_preliminary_id,
    generate_short_app_id,
    generate_shortcut_id,
    steamid64_to_accountid,
)
from nosteam2steam.steam.environment import (
    get_current_user,
    get_latest_proton,
    get_latest_proton_ge,
    get_proton_version,
    get_shortcuts_path,
    get_steam_username,
)

__all__ = [
    "main",
    "add_games_to_shortcuts",
    "save_shortcuts",
    "load_shortcuts",
    "load_games",
    "extract_icon",
    "reindex_shortcuts_alphabetically",
    "get_valid_shortcuts",
    "set_proton_compat_tool",
    "set_proton_compat_tools",
    "STEAMID64_BASE",
    "generate_preliminary_id",
    "generate_app_id",
    "generate_short_app_id",
    "generate_shortcut_id",
    "steamid64_to_accountid",
    "accountid_to_steamid64",
    "get_current_user",
    "get_latest_proton",
    "get_latest_proton_ge",
    "get_proton_version",
    "get_shortcuts_path",
    "get_steam_username",
]
