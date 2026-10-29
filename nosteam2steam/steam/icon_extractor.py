"""Universal Windows PE executable icon extraction module."""

import logging
import os
import struct
from typing import Any, Dict, List, Optional, Tuple

try:
    import pefile
except ImportError:
    pefile = None

logger = logging.getLogger(__name__)


def extract_icon(exe_path: str, output_path: str) -> bool:
    """
    Extracts the highest quality application icon from a Windows PE executable
    and saves it as an .ico file at output_path.
    """
    if pefile is None:
        logger.warning("pefile library is not available. Skipping icon extraction.")
        return False

    if os.path.exists(output_path):
        logger.debug(f"The file {output_path} already exists. Skipping extraction.")
        return True

    if not os.path.isfile(exe_path):
        logger.error(f"Error: File {exe_path} not found.")
        return False

    ico_data = _extract_best_icon_data(exe_path)
    if ico_data is not None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(ico_data)
            logger.info(f"Icon successfully extracted: {output_path}")
            return True
        except OSError as e:
            logger.error(f"Failed to write extracted icon to {output_path}: {e}")
            return False

    logger.error("Icon could not be extracted from executable.")
    return False


def _extract_best_icon_data(exe_path: str) -> Optional[bytes]:
    """Inspects PE resource tables and builds an .ico binary payload from the best icon group."""
    if pefile is None:
        return None

    pe = None
    try:
        pe = pefile.PE(exe_path, fast_load=True)
        resource_dir = pefile.DIRECTORY_ENTRY.get("IMAGE_DIRECTORY_ENTRY_RESOURCE")
        if resource_dir is not None:
            pe.parse_data_directories(directories=[resource_dir])

        dir_res = getattr(pe, "DIRECTORY_ENTRY_RESOURCE", None)
        if not dir_res or not hasattr(dir_res, "entries"):
            return None

        rt_group_id = pefile.RESOURCE_TYPE.get("RT_GROUP_ICON", 14)
        rt_icon_id = pefile.RESOURCE_TYPE.get("RT_ICON", 3)

        group_icons: Dict[Any, bytes] = {}
        icon_images: Dict[Any, bytes] = {}

        for type_entry in dir_res.entries:
            if type_entry.id == rt_group_id and hasattr(type_entry, "directory"):
                for name_entry in type_entry.directory.entries:
                    if hasattr(name_entry, "directory") and name_entry.directory.entries:
                        lang_entry = name_entry.directory.entries[0]
                        if hasattr(lang_entry, "data"):
                            rva = lang_entry.data.struct.OffsetToData
                            size = lang_entry.data.struct.Size
                            data = pe.get_data(rva, size)
                            if data:
                                group_icons[name_entry.id or name_entry.name] = bytes(data)

            elif type_entry.id == rt_icon_id and hasattr(type_entry, "directory"):
                for name_entry in type_entry.directory.entries:
                    if hasattr(name_entry, "directory") and name_entry.directory.entries:
                        lang_entry = name_entry.directory.entries[0]
                        if hasattr(lang_entry, "data"):
                            rva = lang_entry.data.struct.OffsetToData
                            size = lang_entry.data.struct.Size
                            data = pe.get_data(rva, size)
                            if data:
                                icon_images[name_entry.id] = bytes(data)

        if not icon_images:
            return None

        # 1. Primary path: Parse best RT_GROUP_ICON
        if group_icons:
            best_group = _select_best_group_icon(group_icons, icon_images)
            if best_group:
                ico_data = _build_ico_from_group(best_group, icon_images)
                if ico_data:
                    return ico_data

        # 2. Resilient fallback: Construct ICO directly from individual RT_ICON entries
        return _build_ico_from_raw_icons(icon_images)

    except Exception as e:
        logger.error(f"Error reading PE icon resources from {exe_path}: {e}")
        return None
    finally:
        if pe is not None:
            pe.close()


def _parse_image_header(data: bytes) -> Tuple[int, int, int, int]:
    """Accurately parses PNG or DIB image headers to extract (width, height, planes, bit_count)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return w, h, 1, 32
    elif len(data) >= 40:
        bi_size = struct.unpack("<I", data[:4])[0]
        if bi_size == 40:
            w, h, planes, bpp = struct.unpack("<iiHH", data[4:16])
            # In icon DIBs, biHeight is double the display height (XOR + AND masks)
            return abs(w), abs(h) // 2, planes, bpp
    return 32, 32, 1, 32


def _select_best_group_icon(
    group_icons: Dict[Any, bytes], icon_images: Dict[Any, bytes]
) -> Optional[bytes]:
    """Selects the group icon with the highest resolution and color fidelity."""
    best_group = None
    best_score = -1

    for group_id, group_data in group_icons.items():
        if len(group_data) < 6:
            continue
        try:
            num_icons = struct.unpack("<H", group_data[4:6])[0]
            group_max_res = 0
            valid_entries = 0

            for i in range(num_icons):
                offset = 6 + i * 14
                if offset + 14 > len(group_data):
                    break
                w, h, _, _, bpp, _, n_id = struct.unpack("<BBBxHHIH", group_data[offset : offset + 14])
                w = 256 if w == 0 else w
                h = 256 if h == 0 else h
                if n_id in icon_images:
                    valid_entries += 1
                    res_score = w * h * (bpp or 1)
                    if res_score > group_max_res:
                        group_max_res = res_score

            id_bonus = 1000 if group_id in (1, "1", "MAINICON", "IDR_MAINFRAME") else 0
            score = group_max_res + (valid_entries * 10) + id_bonus

            if score > best_score:
                best_score = score
                best_group = group_data
        except Exception:
            continue

    return best_group


def _build_ico_from_group(
    group_data: bytes, icon_images: Dict[Any, bytes]
) -> Optional[bytes]:
    """Constructs complete .ico file payload from a GRPICONDIR structure."""
    if len(group_data) < 6:
        return None

    num_icons = struct.unpack("<H", group_data[4:6])[0]
    entries: List[Dict[str, Any]] = []

    for i in range(num_icons):
        offset = 6 + i * 14
        if offset + 14 > len(group_data):
            break

        w, h, color_count, planes, bit_count, bytes_in_res, n_id = struct.unpack(
            "<BBBxHHIH", group_data[offset : offset + 14]
        )
        if n_id not in icon_images:
            continue

        raw_data = icon_images[n_id]
        if not raw_data:
            continue

        # If data contains trailing alignment padding, slice strictly to bytes_in_res
        data_slice = raw_data[:bytes_in_res] if bytes_in_res > 0 and len(raw_data) >= bytes_in_res else raw_data

        true_w = 256 if w == 0 else w
        true_h = 256 if h == 0 else h
        if true_w >= 256 or true_h >= 256 or bit_count == 0:
            hw, hh, hp, hb = _parse_image_header(data_slice)
            if hw > 0 and hh > 0:
                true_w, true_h = hw, hh
                planes = hp or planes or 1
                bit_count = hb or bit_count or 32

        entries.append(
            {
                "width": true_w,
                "height": true_h,
                "color_count": color_count,
                "planes": planes or 1,
                "bit_count": bit_count or 32,
                "data": data_slice,
            }
        )

    if not entries:
        return None

    return _package_ico_entries(entries)


def _build_ico_from_raw_icons(icon_images: Dict[Any, bytes]) -> Optional[bytes]:
    """Fallback builder that deduces dimensions directly from raw image headers."""
    entries: List[Dict[str, Any]] = []
    for _, raw_data in icon_images.items():
        if len(raw_data) < 40:
            continue
        try:
            w, h, planes, bpp = _parse_image_header(raw_data)
            if w <= 0 or h <= 0:
                continue
            entries.append(
                {
                    "width": w,
                    "height": h,
                    "color_count": 0 if bpp >= 8 else (1 << bpp),
                    "planes": planes,
                    "bit_count": bpp,
                    "data": raw_data,
                }
            )
        except Exception:
            continue

    if not entries:
        return None

    return _package_ico_entries(entries)


def _package_ico_entries(entries: List[Dict[str, Any]]) -> bytes:
    """Sorts icon entries from highest to lowest resolution and builds standard .ico binary."""
    entries.sort(key=lambda x: (-x["width"], -x["height"], -x["bit_count"]))

    header = struct.pack("<HHH", 0, 1, len(entries))
    dir_entries = b""
    image_data = b""
    data_offset = 6 + (16 * len(entries))

    for item in entries:
        w = 0 if item["width"] >= 256 else item["width"]
        h = 0 if item["height"] >= 256 else item["height"]
        data_len = len(item["data"])

        dir_entries += struct.pack(
            "<BBBxHHII",
            w,
            h,
            item.get("color_count", 0),
            item.get("planes", 1),
            item.get("bit_count", 32),
            data_len,
            data_offset,
        )
        image_data += item["data"]
        data_offset += data_len

    return header + dir_entries + image_data


# Backward compatibility wrappers
def standart_extraction_method(exe_path: str) -> Tuple[bool, Optional[bytes]]:
    """Backward-compatible entry point for standard icon extraction."""
    data = _extract_best_icon_data(exe_path)
    return (True, data) if data is not None else (False, None)


def flexible_extraction_method(exe_path: str) -> Tuple[bool, Optional[bytes]]:
    """Backward-compatible entry point for flexible icon extraction."""
    data = _extract_best_icon_data(exe_path)
    return (True, data) if data is not None else (False, None)


__all__ = [
    "extract_icon",
    "flexible_extraction_method",
    "standart_extraction_method",
]
