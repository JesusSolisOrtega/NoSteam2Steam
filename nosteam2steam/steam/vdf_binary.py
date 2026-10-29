"""Binary VDF serialization and deserialization for Steam shortcuts.vdf."""

import logging
import os
import struct
from typing import Any, Dict, Tuple

from nosteam2steam.atomic import atomic_write

logger = logging.getLogger(__name__)


def read_type(reader) -> bytes:
    return reader.read(1)


def read_string(reader) -> str:
    buffer = []
    while True:
        char = reader.read(1)
        if not char or char == b"\x00":
            break
        buffer.append(char)
    return b"".join(buffer).decode("utf-8", errors="replace")


def read_int(reader) -> int:
    data = reader.read(4)
    if len(data) < 4:
        return 0
    return struct.unpack("<I", data)[0]


def read_object(reader) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    while True:
        type_byte = read_type(reader)
        if type_byte == b"\x08":  # VdfType.ObjectEnd
            break
        name = read_string(reader)
        if type_byte == b"\x00":  # VdfType.Object
            result[name] = read_object(reader)
        elif type_byte == b"\x01":  # VdfType.String
            result[name] = read_string(reader)
        elif type_byte == b"\x02":  # VdfType.Int
            result[name] = read_int(reader)
        else:
            raise ValueError(f"Unknown type: {type_byte.hex()}")
    return result


def write_type(writer, value: bytes) -> None:
    writer.write(value)


def write_string(writer, value: str) -> None:
    writer.write(value.encode("utf-8"))
    writer.write(b"\x00")


def write_int(writer, value: int) -> None:
    writer.write(struct.pack("<I", value & 0xFFFFFFFF))


def write_object(writer, value: Dict[str, Any]) -> None:
    for name, sub_object in value.items():
        if isinstance(sub_object, dict):
            write_type(writer, b"\x00")  # VdfType.Object
            write_string(writer, name)
            write_object(writer, sub_object)
        elif isinstance(sub_object, str):
            write_type(writer, b"\x01")  # VdfType.String
            write_string(writer, name)
            write_string(writer, sub_object)
        elif isinstance(sub_object, int):
            write_type(writer, b"\x02")  # VdfType.Int
            write_string(writer, name)
            write_int(writer, sub_object)
    write_type(writer, b"\x08")  # VdfType.ObjectEnd


def load_shortcuts(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        return read_object(f).get("shortcuts", {})


def get_valid_shortcuts(shortcuts_path: str) -> Tuple[Dict[str, Any], int]:
    all_shortcuts = load_shortcuts(shortcuts_path)
    valid_shortcuts = {}
    removed_count = 0

    for key, value in all_shortcuts.items():
        exe_path = value.get("Exe", "").strip('"')
        if os.path.exists(os.path.expanduser(exe_path)):
            valid_shortcuts[key] = value
        else:
            removed_count += 1

    return valid_shortcuts, removed_count


def reindex_shortcuts_alphabetically(shortcuts: Dict[str, Any]) -> Dict[str, Any]:
    sorted_shortcuts = sorted(shortcuts.items(), key=lambda x: x[1].get("appname", "").lower())

    reindexed = {}
    for new_index, (_, shortcut_data) in enumerate(sorted_shortcuts):
        reindexed[str(new_index)] = shortcut_data

    logger.info(f"Reindexed {len(reindexed)} shortcuts alphabetically")
    return reindexed


def save_shortcuts(path: str, shortcuts: Dict[str, Any]) -> None:
    try:
        with atomic_write(path, mode="wb", backup=True) as f:
            write_object(f, {"shortcuts": shortcuts})
        logger.info(f"shortcuts.vdf file updated successfully at {path}")
    except Exception as e:
        logger.error(f"Error saving shortcuts to {path}: {e}")
        raise
