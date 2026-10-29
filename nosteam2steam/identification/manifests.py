"""Ludusavi and Game Backup Monitor manifest download and indexing subsystem."""

import os
import io
import time
import json
import pickle
import logging
import requests
import xml.etree.ElementTree as ET
import yaml
from yaml import CSafeLoader as SafeLoader
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List

from nosteam2steam.config import XML_FILE, YAML_FILE, XML_URL, YAML_URL, INDEX_DIR

logger = logging.getLogger(__name__)

MANIFEST_TTL_SECONDS = 86400  # 24 hours


def download_file(url: str, destination: str, force: bool = False) -> bool:
    try:
        if not force and os.path.exists(destination):
            file_age = time.time() - os.path.getmtime(destination)
            if file_age < MANIFEST_TTL_SECONDS:
                logger.debug(f"File {destination} is within TTL ({int(file_age)}s old); skipping remote checks.")
                return False

        response = requests.head(url, allow_redirects=True, timeout=10)
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

        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with open(destination, "wb") as file:
            file.write(response.content)
        logger.info(f"File downloaded and saved to: {destination}")

        if remote_etag:
            with open(destination + ".etag", "w") as f:
                f.write(remote_etag)

        return True
    except requests.RequestException as e:
        logger.error(f"Error downloading file {url}: {e}")
        return False


def load_yaml_file(file_path: str) -> Optional[Dict]:
    try:
        with open(file_path, "rb") as f:
            data = f.read()
            try:
                return yaml.load(io.BytesIO(data), Loader=SafeLoader)
            except Exception:
                return yaml.safe_load(data.decode("utf-8"))
    except Exception as e:
        logger.error(f"Error loading YAML: {str(e)[:200]}")
        return None


def index_xml_data(root: ET.Element) -> Dict[str, str]:
    xml_index = {}
    for game in root.findall("Game"):
        name_elem = game.find("Name")
        proc_elem = game.find("ProcessName")
        game_name = name_elem.text if name_elem is not None and name_elem.text else None
        process_name = proc_elem.text if proc_elem is not None and proc_elem.text else None
        if game_name and process_name:
            xml_index[process_name.lower()] = game_name
    return xml_index


def index_yaml_data(yaml_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    index: Dict[str, Any] = {
        "_metadata": [],
        "by_exe": {},
        "by_path": {},
        "by_install_dir": {},
        "by_gog_id": {},
        "by_steam_id": {},
        "by_name": {},
        "by_name_fuzzy": {},
    }

    if not yaml_data:
        return index

    metadata_list: List[Dict[str, Any]] = []
    cache: Dict[str, int] = {}

    for yaml_game_name, yaml_game_data in yaml_data.items():
        metadata = {
            "game_name": yaml_game_name,
            "steam_id": yaml_game_data.get("steam", {}).get("id"),
            "lutris_id": yaml_game_data.get("id", {}).get("lutris"),
            "gog_id": yaml_game_data.get("gog", {}).get("id"),
            "alias": yaml_game_data.get("alias"),
            "files": yaml_game_data.get("files", {}),
        }

        metadata_str = json.dumps(metadata, sort_keys=True)
        if metadata_str not in cache:
            meta_idx = len(metadata_list)
            metadata_list.append(metadata)
            cache[metadata_str] = meta_idx
        else:
            meta_idx = cache[metadata_str]

        normalized_name = yaml_game_name.lower()
        index["by_name"][normalized_name] = meta_idx

        name_parts = set(normalized_name.split())
        for part in name_parts:
            if len(part) > 2:
                if part not in index["by_name_fuzzy"]:
                    index["by_name_fuzzy"][part] = []
                index["by_name_fuzzy"][part].append(meta_idx)

        if metadata["alias"]:
            aliases = [metadata["alias"]] if isinstance(metadata["alias"], str) else metadata["alias"]
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
            install_dir = (
                yaml_game_data["installDir"].lower()
                if isinstance(yaml_game_data["installDir"], str)
                else next(iter(yaml_game_data["installDir"].keys()), "").lower()
            )
            index["by_install_dir"][install_dir] = {"_meta": meta_idx, "launch": yaml_game_data.get("launch", {})}

        launch_data = yaml_game_data.get("launch", {})
        for launch_path in launch_data:
            if launch_path.startswith("<base>/"):
                path_key = launch_path[7:].lower()
                index["by_path"][path_key] = meta_idx

            exe_name = os.path.basename(launch_path).lower()
            if exe_name:
                index["by_exe"][exe_name] = meta_idx

    index["_metadata"] = metadata_list
    return index


def save_index_to_file(index: Dict, file_path: str) -> None:
    try:
        with open(file_path, "w", encoding="utf-8", buffering=2**18) as file:
            json.dump(index, file, ensure_ascii=False, separators=(",", ":"), check_circular=False, allow_nan=False)
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
            futures["xml"] = executor.submit(lambda: index_xml_data(ET.parse(XML_FILE).getroot()))

        if yaml_changed or not os.path.exists(os.path.join(index_dir, "yaml_index.json")):
            futures["yaml"] = executor.submit(lambda: index_yaml_data(load_yaml_file(YAML_FILE)))

        for index_type, future in futures.items():
            try:
                indexes[index_type] = future.result()
                save_index_to_file(indexes[index_type], os.path.join(index_dir, f"{index_type}_index.json"))
            except Exception as e:
                logger.error(f"Error indexing {index_type}: {str(e)[:100]}")

    logger.info("PCGW indexes updated successfully.")
    return indexes


def verify_and_download_files() -> Dict[str, Any]:
    if not os.path.exists(XML_FILE):
        logger.info(f"XML file not found in path: {XML_FILE}, downloading...")
        if not download_file(XML_URL, XML_FILE):
            logger.error("Unable to download the XML file.")

    if not os.path.exists(YAML_FILE):
        logger.info(f"YAML file not found in path: {YAML_FILE}, downloading...")
        if not download_file(YAML_URL, YAML_FILE):
            logger.error("Unable to download the YAML file.")

    return create_or_update_indexes()


class ManifestRepository:
    """Encapsulates manifest indexing, caching, and multi-key querying."""

    def __init__(self, index_dir: str = INDEX_DIR, preloaded: Optional[Dict[str, Any]] = None):
        self.index_dir = index_dir
        self.index_files = {
            "xml": os.path.join(index_dir, "xml_index.json"),
            "yaml": os.path.join(index_dir, "yaml_index.json"),
        }
        self.xml_index: Dict[str, str] = {}
        self.by_exe: Dict[str, Dict[str, Any]] = {}
        self.by_path: Dict[str, Dict[str, Any]] = {}
        self.by_install_dir: Dict[str, Dict[str, Any]] = {}
        self.by_gog_id: Dict[str, Dict[str, Any]] = {}
        self.by_steam_id: Dict[str, Dict[str, Any]] = {}
        self.by_name: Dict[str, Dict[str, Any]] = {}
        self.by_name_fuzzy: Dict[str, List[Dict[str, Any]]] = {}
        self._load(preloaded)

    def _load(self, preloaded: Optional[Dict[str, Any]] = None, first_attempt: bool = True) -> None:
        pickle_views_path = os.path.join(self.index_dir, "manifest_views.pkl")
        yaml_index_path = self.index_files["yaml"]

        # Fast path: check if binary views cache is present and up-to-date
        is_pickle_fresh = os.path.exists(pickle_views_path) and (
            not os.path.exists(yaml_index_path) or os.path.getmtime(pickle_views_path) >= os.path.getmtime(yaml_index_path)
        )
        if preloaded is None and is_pickle_fresh:
            try:
                with open(pickle_views_path, "rb") as pf:
                    cached = pickle.load(pf)
                self.xml_index = cached.get("xml_index", {})
                self.by_exe = cached.get("by_exe", {})
                self.by_path = cached.get("by_path", {})
                self.by_install_dir = cached.get("by_install_dir", {})
                self.by_gog_id = cached.get("by_gog_id", {})
                self.by_steam_id = cached.get("by_steam_id", {})
                self.by_name = cached.get("by_name", {})
                self.by_name_fuzzy = cached.get("by_name_fuzzy", {})
                logger.debug("Loaded pre-computed manifest views from binary cache (manifest_views.pkl).")
                return
            except Exception as e:
                logger.debug(f"Could not load binary manifest views cache: {e}")

        idx = preloaded or {k: load_index_from_file(v) for k, v in self.index_files.items()}
        if not all(idx.values()):
            if first_attempt:
                logger.info("Generating manifest indexes...")
                create_or_update_indexes()
                return self._load(first_attempt=False)
            logger.error("Could not load manifest indexes.")
            return

        self.xml_index = idx.get("xml") or {}
        if yaml_data := idx.get("yaml"):
            meta = yaml_data.get("_metadata", [])
            valid = lambda i: i < len(meta)
            self.by_exe = {k: meta[i] for k, i in yaml_data.get("by_exe", {}).items() if valid(i)}
            self.by_path = {k: meta[i] for k, i in yaml_data.get("by_path", {}).items() if valid(i)}
            self.by_install_dir = {
                k: {**meta[d["_meta"]], "launch": d.get("launch", {})}
                for k, d in yaml_data.get("by_install_dir", {}).items()
                if valid(d.get("_meta", -1))
            }
            self.by_gog_id = {k: meta[i] for k, i in yaml_data.get("by_gog_id", {}).items() if valid(i)}
            self.by_steam_id = {k: meta[i] for k, i in yaml_data.get("by_steam_id", {}).items() if valid(i)}
            self.by_name = {k: meta[i] for k, i in yaml_data.get("by_name", {}).items() if valid(i)}
            self.by_name_fuzzy = {
                k: [meta[i] for i in list(dict.fromkeys(ids)) if valid(i)]
                for k, ids in yaml_data.get("by_name_fuzzy", {}).items()
            }

            try:
                views_data = {
                    "xml_index": self.xml_index,
                    "by_exe": self.by_exe,
                    "by_path": self.by_path,
                    "by_install_dir": self.by_install_dir,
                    "by_gog_id": self.by_gog_id,
                    "by_steam_id": self.by_steam_id,
                    "by_name": self.by_name,
                    "by_name_fuzzy": self.by_name_fuzzy,
                }
                with open(pickle_views_path, "wb") as pf:
                    pickle.dump(views_data, pf, protocol=pickle.HIGHEST_PROTOCOL)
                logger.debug("Saved pre-computed manifest views to manifest_views.pkl.")
            except Exception as e:
                logger.debug(f"Could not save binary manifest views cache: {e}")

    def get_by_steam_id(self, steam_id: str) -> Optional[Dict[str, Any]]:
        return self.by_steam_id.get(steam_id)

    def get_by_gog_id(self, gog_id: str) -> Optional[Dict[str, Any]]:
        return self.by_gog_id.get(gog_id)

    def get_by_path(self, rel_path: str) -> Optional[Dict[str, Any]]:
        return self.by_path.get(rel_path)

    def get_by_exe(self, exe_name: str) -> Optional[Dict[str, Any]]:
        return self.by_exe.get(exe_name.lower())

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        return self.by_name.get(name.lower())

    def get_xml_game_name(self, stem: str) -> Optional[str]:
        return self.xml_index.get(stem.lower())

    def get_fuzzy_matches(self, term: str) -> List[Dict[str, Any]]:
        return self.by_name_fuzzy.get(term.lower(), [])

    @property
    def _views(self) -> Dict[str, Any]:
        return {
            "xml": self.xml_index,
            "yaml_by_exe": self.by_exe,
            "yaml_by_path": self.by_path,
            "yaml_by_install_dir": self.by_install_dir,
            "yaml_by_gog_id": self.by_gog_id,
            "yaml_by_steam_id": self.by_steam_id,
            "yaml_by_name": self.by_name,
            "yaml_by_name_fuzzy": self.by_name_fuzzy,
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self._views.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._views[key]


_default_manifest_repository: Optional[ManifestRepository] = None


def get_manifest_repository(index_dir: str = INDEX_DIR, force_reload: bool = False) -> ManifestRepository:
    """Returns a memoized, process-wide ManifestRepository instance."""
    global _default_manifest_repository
    if _default_manifest_repository is None or force_reload:
        _default_manifest_repository = ManifestRepository(index_dir=index_dir)
    return _default_manifest_repository
