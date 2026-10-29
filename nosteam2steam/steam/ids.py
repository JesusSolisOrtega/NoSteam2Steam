"""Mathematical calculations and conversions for SteamID, AppID, and shortcut IDs."""

import binascii

STEAMID64_BASE = 76561197960265728


def generate_preliminary_id(exe: str, app_name: str) -> int:
    """Calculates internal 64-bit preliminary ID based on executable and game title CRC32."""
    key = (exe + app_name).encode("utf-8")
    crc32_hash = binascii.crc32(key)
    top = crc32_hash | 0x80000000
    return (top << 32) | 0x02000000


def generate_app_id(exe: str, app_name: str) -> str:
    """Returns full 64-bit unsigned AppID as string."""
    return str(generate_preliminary_id(exe, app_name))


def generate_short_app_id(exe: str, app_name: str) -> str:
    """Returns upper 32-bit AppID string used in Proton compatdata directory names."""
    return str(generate_preliminary_id(exe, app_name) >> 32)


def generate_shortcut_id(exe: str, app_name: str) -> int:
    """Returns signed 32-bit integer shortcut ID used in shortcuts.vdf."""
    return (generate_preliminary_id(exe, app_name) >> 32) - 0x100000000


def steamid64_to_accountid(steamid64: int | str) -> int:
    """Converts a 64-bit SteamID to a 32-bit AccountID."""
    return int(steamid64) - STEAMID64_BASE


def accountid_to_steamid64(accountid: int | str) -> int:
    """Converts a 32-bit AccountID to a 64-bit SteamID."""
    return int(accountid) + STEAMID64_BASE
