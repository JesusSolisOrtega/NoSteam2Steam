"""Archive manipulation and metadata manifest handling for 7z game saves."""

from datetime import datetime  # noqa: F401
from fnmatch import fnmatch
import logging
import os
from pathlib import Path
import shutil
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
import py7zr

logger = logging.getLogger(__name__)


def process_filetype(base_path, file_type):
    """
    Finds files matching pattern definitions (e.g. 'pattern:subdir' or wildcard glob).
    """
    base_path = Path(base_path)
    if base_path.is_dir():
        base_dir = base_path
    else:
        base_dir = base_path.parent

    matching_files = []
    patterns = [p.strip() for p in file_type.split(":") if p.strip()]

    for pattern in patterns:
        if ":" in pattern and "*" not in pattern:
            file, subdir = pattern.split(":", 1)
            search_path = base_dir / subdir.strip()
            target_candidate = search_path / file.strip()
            if target_candidate.is_file():
                matching_files.append(target_candidate)
            continue

        if "*" in pattern and ("/" in pattern or "\\" in pattern):
            folder_part, file_part = pattern.replace("\\", "/").rsplit("/", 1)
            for match_dir in base_dir.glob(folder_part):
                if match_dir.is_dir():
                    for file in match_dir.glob(file_part):
                        if file.is_file() and fnmatch(file.name, file_part):
                            matching_files.append(file)
            continue

        for file in base_dir.rglob(pattern):
            if file.is_file() and fnmatch(file.name, pattern.split("/")[-1]):
                matching_files.append(file)

    return list(set(matching_files))


def verify_archive_integrity(archive_path: Path | str) -> bool:
    """Verifies archive block headers and decompression integrity using py7zr."""
    try:
        with py7zr.SevenZipFile(archive_path, mode="r") as z:
            z.test()
        return True
    except Exception as e:
        logger.error(f"Archive integrity verification failed for {archive_path}: {e}")
        return False


def create_file_7z_gbm(source_paths, metadata, target_dir, file_name):
    """
    Creates a .7z archive containing game saves and a Game Backup Monitor XML manifest.
    """
    target_dir = Path(target_dir)
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
        "FileType": metadata.get("FileType", "") or "",
        "ExcludeList": metadata.get("ExcludeList", "") or "",
        "MonitorOnly": "false",
        "Comments": "",
        "IsRegEx": "false",
        "RecurseSubFolders": "true",
        "OS": str(metadata["os_code"]),
        "UseWindowTitle": "false",
        "Differential": "false",
        "DiffInterval": "0",
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
    temp_7z_file = target_dir / f".{file_name}.tmp_{uuid.uuid4().hex}"
    try:
        with open(temp_xml_path, "wb") as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            ET.ElementTree(root).write(f, encoding="utf-8")

        with py7zr.SevenZipFile(temp_7z_file, "w") as z:
            for source_path in source_paths:
                source_path = Path(source_path)
                if source_path.is_dir():
                    for item_path in source_path.rglob("*"):
                        arcname = str(item_path.relative_to(source_path))
                        z.write(item_path, arcname=arcname)
                else:
                    z.write(source_path, arcname=source_path.name)

            if "<winreg" in str(metadata.get("original_path", "")).lower():
                from nosteam2steam.backup.registry import export_proton_registry_section

                for sp in source_paths:
                    sp_path = Path(sp)
                    pfx_dir = sp_path if (sp_path / "user.reg").exists() else sp_path.parent
                    exported = export_proton_registry_section(pfx_dir, str(metadata.get("original_path", "")))
                    if exported:
                        z.writestr(exported, arcname="_registry_backup.reg")
                        break

            z.write(temp_xml_path, arcname="_gbm_backup_metadata.xml")

        # Verify archive block integrity before rotating and committing
        if not verify_archive_integrity(temp_7z_file):
            raise IOError(f"Archive integrity verification failed for staged file: {temp_7z_file}")

        # Preserve previous backup as .bak before replacing
        bak_file = file_7z.with_name(f"{file_7z.name}.bak")
        if file_7z.exists():
            try:
                os.replace(file_7z, bak_file)
            except OSError as e:
                logger.warning(f"Could not rotate previous backup to .bak: {e}")

        # Atomic replacement once compression and verification finish successfully
        os.replace(temp_7z_file, file_7z)

    except Exception as e:
        logger.error(f"Error creating 7z file: {e}")
        if temp_7z_file.exists():
            temp_7z_file.unlink(missing_ok=True)
        if file_7z.exists():
            file_7z.unlink(missing_ok=True)
        raise
    finally:
        temp_xml_path.unlink(missing_ok=True)
        if temp_7z_file.exists():
            temp_7z_file.unlink(missing_ok=True)

    return file_7z


def load_metadata_from_7z(file_path_7z):
    """
    Extracts and parses _gbm_backup_metadata.xml from a .7z archive.
    """
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with py7zr.SevenZipFile(file_path_7z, mode="r") as file_7z:
                file_7z.extract(path=tmp_dir, targets=["_gbm_backup_metadata.xml"])

            meta_file = Path(tmp_dir) / "_gbm_backup_metadata.xml"
            if not meta_file.exists():
                return None

            with open(meta_file, "r", encoding="utf-8") as file_xml:
                tree = ET.parse(file_xml)
                root = tree.getroot()

                game_name = root.findtext(".//GameData/Name")
                original_path = root.findtext(".//GameData/Path")
                if not game_name or not original_path:
                    logger.info("Error: Metadata file does not contain required information.")
                    return None

                metadata = {
                    "game_name": game_name,
                    "original_path": original_path,
                    "folder_save": root.findtext(".//GameData/FolderSave"),
                    "process_name": root.findtext(".//GameData/ProcessName"),
                }
                return metadata
    except Exception as e:
        logger.info(f"Error reading metadata file: {e}")
        return None


def _copy_folder_7z(file_path_7z, destination_path):
    try:
        destination_path = Path(destination_path)
        destination_path.mkdir(parents=True, exist_ok=True)

        with py7zr.SevenZipFile(file_path_7z, mode="r") as file_7z:
            file_7z.extractall(path=destination_path)

        metadata_path = destination_path / "_gbm_backup_metadata.xml"
        if metadata_path.exists():
            metadata_path.unlink()

        reg_file = destination_path / "_registry_backup.reg"
        if reg_file.exists():
            from nosteam2steam.backup.registry import merge_proton_registry_section

            pfx_candidate = destination_path if (destination_path / "user.reg").exists() else destination_path.parent
            if (pfx_candidate / "user.reg").exists():
                merge_proton_registry_section(pfx_candidate, reg_file.read_text(encoding="utf-8", errors="replace"))
            reg_file.unlink(missing_ok=True)

        if not any(destination_path.iterdir()):
            logger.error(f"7z file {file_path_7z} is empty or contains no valid data")
            return False

        return True

    except Exception as e:
        logger.error(f"Error extracting {file_path_7z}: {str(e)}")
        dest_p = Path(destination_path)
        if dest_p.exists():
            shutil.rmtree(dest_p, ignore_errors=True)
        return False


def _copy_file_7z(file_path_7z, destination_file_path):
    try:
        dest_p = Path(destination_file_path)
        dest_p.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_path = Path(tmp_dir)
            with py7zr.SevenZipFile(file_path_7z, mode="r") as file_7z:
                file_7z.extractall(path=temp_path)

            valid_files = [f for f in temp_path.rglob("*") if f.is_file() and f.name != "_gbm_backup_metadata.xml"]

            if not valid_files:
                logger.error(f"No valid files found in {file_path_7z}")
                return False

            temp_file = valid_files[0]
            shutil.copy2(str(temp_file), str(dest_p))

            return True

    except Exception as e:
        logger.error(f"Error copying file from {file_path_7z}: {str(e)}")
        return False


def extract_archive(file_path_7z, destination_path, is_folder=True):
    """
    Extracts files from a .7z backup to target destination path.
    """
    logger.info(f"Starting extraction from {file_path_7z} to {destination_path}")
    if is_folder:
        return _copy_folder_7z(file_path_7z, destination_path)
    return _copy_file_7z(file_path_7z, destination_path)


copy_saves = extract_archive


def update_archive(file_path_7z, source_path, metadata=None):
    """
    Updates an existing .7z backup archive with files from source_path.
    """
    file_7z_path = Path(file_path_7z)
    source_path = Path(source_path)
    temp_dir = Path("temp_steamdeck")
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Preserve .bak copy of archive before modifying
    if file_7z_path.exists():
        bak_file = file_7z_path.with_name(f"{file_7z_path.name}.bak")
        try:
            shutil.copy2(file_7z_path, bak_file)
        except OSError as e:
            logger.warning(f"Could not copy backup to .bak: {e}")

    try:
        is_folder = metadata.get("folder_save", True) if metadata else True
        file_type = metadata.get("FileType", "") if metadata else ""

        if is_folder:
            if not source_path.exists():
                raise ValueError(f"Path not found: {source_path}")

            for file in source_path.rglob("*"):
                if file.is_file():
                    relative_path = file.relative_to(source_path)
                    destination_path = temp_dir / relative_path
                    destination_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, destination_path)
        else:
            if file_type:
                files_to_copy = process_filetype(source_path, file_type)
                if not files_to_copy:
                    raise ValueError(f"No files matching: {file_type}")

                for file in files_to_copy:
                    rel_base = source_path.parent if source_path.is_dir() else source_path
                    relative_path = file.relative_to(rel_base)
                    destination_path = temp_dir / relative_path
                    destination_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, destination_path)
            else:
                if not source_path.is_file():
                    raise ValueError(f"File not found: {source_path}")
                shutil.copy2(source_path, temp_dir / source_path.name)

        with py7zr.SevenZipFile(file_path_7z, mode="a") as file_7z:
            for file in temp_dir.rglob("*"):
                if file.is_file():
                    path_7z = file.relative_to(temp_dir)
                    file_7z.write(file, str(path_7z).replace("\\", "/"))

        # Verify archive integrity after modification
        if not verify_archive_integrity(file_path_7z):
            logger.error(f"Archive verification failed after update for {file_path_7z}; rolling back to .bak")
            bak_file = file_7z_path.with_name(f"{file_7z_path.name}.bak")
            if bak_file.exists():
                os.replace(bak_file, file_7z_path)
            return False

        logger.info(f"Backup updated successfully: {file_path_7z}")
        return True

    except Exception as e:
        logger.error(f"Error updating backup: {str(e)}")
        return False
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


update_backup = update_archive
