"""Steam grid and artwork management subsystem."""

import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import quote
import requests

from nosteam2steam.steam.icon_extractor import extract_icon

logger = logging.getLogger(__name__)


def download_image(url: str, path: str) -> bool:
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "NoSteam2Steam/1.0"})
        if response.status_code == 200 and len(response.content) > 0:
            with open(path, "wb") as f:
                f.write(response.content)
            return True
        else:
            logger.debug(f"Could not download image from {url}. Status code: {response.status_code}")
    except Exception as e:
        logger.debug(f"Error downloading image from {url}: {e}")
    return False


def search_steam_app_id(game_name: str) -> Optional[str]:
    """Resolves Steam AppID using public Steam Store search API."""
    if not game_name:
        return None
    try:
        url = f"https://store.steampowered.com/api/storesearch/?term={quote(game_name)}&l=english&cc=US"
        response = requests.get(url, timeout=5, headers={"User-Agent": "NoSteam2Steam/1.0"})
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            if items:
                return str(items[0]["id"])
    except Exception as e:
        logger.debug(f"Error querying Steam Store search for {game_name}: {e}")
    return None


def get_steam_images(app_id: str) -> Dict[str, str]:
    """Gets image URLs from Steam Akamai CDN."""
    base_url = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}"
    return {
        "header": f"{base_url}/header.jpg",
        "library_hero": f"{base_url}/library_hero.jpg",
        "logo": f"{base_url}/logo.png",
        "library_600x900": f"{base_url}/library_600x900.jpg",
    }


def get_gog_images(gog_id: str) -> Dict[str, str]:
    """Gets official artwork URLs from GOG Galaxy public product API."""
    if not gog_id:
        return {}
    try:
        url = f"https://api.gog.com/products/{gog_id}"
        response = requests.get(url, timeout=4, headers={"User-Agent": "NoSteam2Steam/1.0"})
        if response.status_code == 200:
            data = response.json()
            images = data.get("images", {})

            def _norm(u: Optional[str]) -> str:
                if not u:
                    return ""
                return f"https:{u}" if u.startswith("//") else u

            return {
                "icon": _norm(images.get("icon")),
                "sidebar_icon": _norm(images.get("sidebarIcon")),
                "background": _norm(images.get("background")),
                "logo": _norm(images.get("logo")),
            }
    except Exception as e:
        logger.debug(f"Error fetching GOG images for ID {gog_id}: {e}")
    return {}


def save_grid_images(
    app_id_short: str,
    user_config_dir: str,
    game_data: Dict[str, Any],
    bigpicture_appid: Optional[str] = None,
    exe_path: Optional[str] = None,
) -> Dict[str, str]:
    """
    Downloads and caches all personalized Steam grid assets for a non-Steam shortcut:
    1. Vertical capsule / Poster: 600x900 (<app_id_short>p.jpg)
    2. Hero background: 1920x620 (<app_id_short>_hero.jpg)
    3. Transparent title logo: PNG (<app_id_short>_logo.png)
    4. Classic horizontal banner: 460x215 (<app_id_short>.jpg)
    5. Big Picture legacy banner: (<bigpicture_appid>.jpg)
    6. Shortcut icon: (<app_id_short>.ico / .png) in icons/ directory

    Constructs a cascading resolution across available providers (Steam, GOG, Lutris),
    retaining local PE executable extraction as an emergency fallback for the icon.
    """
    grid_path = os.path.join(user_config_dir, "grid")
    icons_path = os.path.join(user_config_dir, "icons")
    os.makedirs(grid_path, exist_ok=True)
    os.makedirs(icons_path, exist_ok=True)

    providers = game_data.get("providers", [])
    steam_appid = next((p["id"] for p in providers if p.get("service") == "steam"), None)
    gog_id = next((p["id"] for p in providers if p.get("service") == "gog"), None)

    if not steam_appid and game_data.get("name"):
        steam_appid = search_steam_app_id(game_data["name"])

    steam_images = get_steam_images(steam_appid) if steam_appid else {}
    gog_images = get_gog_images(gog_id) if gog_id else {}

    lutris_images = {
        "header": game_data.get("banner_url", ""),
        "library_hero": game_data.get("background_image", "") or game_data.get("banner_url", ""),
        "logo": "",
        "library_600x900": game_data.get("coverart", ""),
        "icon": game_data.get("icon_url", ""),
    }

    asset_candidates = {
        "header": [steam_images.get("header"), lutris_images.get("header")],
        "library_hero": [
            steam_images.get("library_hero"),
            gog_images.get("background"),
            lutris_images.get("library_hero"),
        ],
        "logo": [steam_images.get("logo"), gog_images.get("logo"), lutris_images.get("logo")],
        "library_600x900": [steam_images.get("library_600x900"), lutris_images.get("library_600x900")],
    }

    image_files = {
        "header": os.path.join(grid_path, f"{app_id_short}.jpg"),
        "library_hero": os.path.join(grid_path, f"{app_id_short}_hero.jpg"),
        "logo": os.path.join(grid_path, f"{app_id_short}_logo.png"),
        "library_600x900": os.path.join(grid_path, f"{app_id_short}p.jpg"),
    }

    result_mapping: Dict[str, str] = {}

    for key, target_path in image_files.items():
        if os.path.exists(target_path):
            result_mapping[key] = target_path
            continue

        for candidate_url in asset_candidates.get(key, []):
            if candidate_url and download_image(candidate_url, target_path):
                result_mapping[key] = target_path
                break

    if bigpicture_appid:
        bigpicture_image_path = os.path.join(grid_path, f"{bigpicture_appid}.jpg")
        header_file = image_files.get("header")
        if header_file and not os.path.exists(bigpicture_image_path) and os.path.exists(header_file):
            try:
                import shutil

                shutil.copyfile(header_file, bigpicture_image_path)
            except Exception as e:
                logger.debug(f"Error copying image for Big Picture: {e}")

    icon_resolved = False

    # 1. Primary: Download official network icon (GOG high-res PNG, then Lutris icon)
    network_icon_candidates = [gog_images.get("icon"), lutris_images.get("icon")]
    for icon_url in network_icon_candidates:
        if icon_url and icon_url.startswith(("http://", "https://")):
            ext = "ico" if icon_url.lower().endswith(".ico") else "png"
            network_icon_path = os.path.join(icons_path, f"{app_id_short}.{ext}")
            if os.path.exists(network_icon_path) or download_image(icon_url, network_icon_path):
                result_mapping["icon"] = network_icon_path
                icon_resolved = True
                break

    # 2. Emergency fallback: Extract embedded icon from executable if network icon failed or is absent
    if not icon_resolved and exe_path and os.path.exists(exe_path):
        fallback_icon_path = os.path.join(icons_path, f"{app_id_short}.ico")
        if os.path.exists(fallback_icon_path) or extract_icon(exe_path, fallback_icon_path):
            result_mapping["icon"] = fallback_icon_path
            icon_resolved = True

    return result_mapping
