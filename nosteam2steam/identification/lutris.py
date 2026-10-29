"""Lutris API integration and metadata enhancement subsystem."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

LUTRIS_API_URL = "https://lutris.net/api/games"
REQUEST_TIMEOUT = 6
MAX_RETRIES = 3
BACKOFF_FACTOR = 1
STATUS_FORCELIST = [500, 502, 503, 504]


def create_lutris_session() -> requests.Session:
    """Creates a configured requests.Session with connection pooling and exponential backoff."""
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=STATUS_FORCELIST,
        allowed_methods=["HEAD", "GET", "OPTIONS"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=100, pool_maxsize=100, pool_block=False)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"Accept": "application/json", "User-Agent": "NoSteam2Steam/1.2"})
    return session


def search_lutris_games(query_name: str, session: Optional[requests.Session] = None) -> List[Dict[str, Any]]:
    """Queries the Lutris search API endpoint and returns candidate game records."""
    query_name = str(query_name).strip()
    if not query_name:
        return []
    url = f"{LUTRIS_API_URL}?search={quote(query_name)}"
    headers = {"Accept": "application/json", "User-Agent": "NoSteam2Steam/1.2"}
    caller = session.get if session is not None else requests.get
    try:
        response = caller(url, timeout=REQUEST_TIMEOUT, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                return data.get("results", [])
    except Exception as e:
        logger.warning(f"Error querying Lutris API for '{query_name}': {e}")
    return []


def query_lutris_game_by_slug(slug: str, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
    """Queries Lutris API for a specific game slug or ID."""
    slug = str(slug).strip()
    if not slug:
        return None
    url = f"{LUTRIS_API_URL}/{quote(slug)}"
    headers = {"Accept": "application/json", "User-Agent": "NoSteam2Steam/1.2"}
    caller = session.get if session is not None else requests.get
    try:
        response = caller(url, timeout=REQUEST_TIMEOUT, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.debug(f"Lutris slug lookup failed for '{slug}': {e}")
    return None


def merge_providers(
    original_providers: List[Dict[str, Any]], lutris_providers: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Merges provider records deduplicating by normalized service name."""
    merged: List[Dict[str, Any]] = []
    known_services = set()
    for provider in lutris_providers:
        service = provider.get("service", "").lower()
        if service:
            merged.append(provider)
            known_services.add(service)
    for provider in original_providers:
        service = provider.get("service", "").lower()
        if service and service not in known_services:
            merged.append(provider)
            known_services.add(service)
    return merged


def format_lutris_game_data(
    lutris_data: Optional[Dict[str, Any]],
    fallback_name: str = "",
    original_providers: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Formats Lutris game metadata into canonical games.json schema."""
    original_providers = original_providers or []
    if not lutris_data:
        return {
            "name": fallback_name,
            "slug": fallback_name.lower().replace(" ", "-") if fallback_name else "",
            "source": "Manual",
            "platforms": ["PC"],
            "released": "",
            "background_image": "",
            "rating": "",
            "metacritic": "",
            "banner_url": "",
            "icon_url": "",
            "coverart": "",
            "providers": original_providers,
        }

    platforms = [p["name"] for p in lutris_data.get("platforms", []) if isinstance(p, dict) and p.get("name")] or ["PC"]

    lutris_providers: List[Dict[str, Any]] = []
    for provider in lutris_data.get("provider_games", []):
        if isinstance(provider, dict) and (service := provider.get("service", "").lower()):
            lutris_providers.append(
                {"name": provider.get("name", ""), "service": service, "id": str(provider.get("slug", ""))}
            )

    known_services = {p["service"].lower() for p in lutris_providers}
    if (steamid := lutris_data.get("steamid")) and "steam" not in known_services:
        lutris_providers.append(
            {"name": lutris_data.get("name", fallback_name), "service": "steam", "id": str(steamid)}
        )
    if (gogid := lutris_data.get("gogid")) and "gog" not in known_services:
        lutris_providers.append(
            {"name": lutris_data.get("name", fallback_name), "service": "gog", "id": str(gogid)}
        )

    providers = merge_providers(original_providers, lutris_providers)
    bg_image = lutris_data.get("background_image") or lutris_data.get("coverart") or ""

    return {
        "name": lutris_data.get("name", fallback_name),
        "slug": lutris_data.get("slug", ""),
        "source": "Lutris",
        "platforms": platforms,
        "released": str(lutris_data.get("year", "")),
        "background_image": bg_image,
        "rating": str(lutris_data.get("rating", "")),
        "metacritic": str(lutris_data.get("metacritic", "")),
        "banner_url": lutris_data.get("banner_url", ""),
        "icon_url": lutris_data.get("icon_url", ""),
        "coverart": lutris_data.get("coverart", ""),
        "providers": providers,
    }


class LutrisDataEnhancer:
    """Discovers, matches, and enriches game metadata concurrently via the Lutris API."""

    def __init__(self, associate_data: Dict[str, Dict]):
        self.associate_data = associate_data
        self.session = create_lutris_session()

    def _find_best_match(
        self, game_data: Dict[str, Any], candidates: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        if steam_id := str(game_data.get("steam_id", "")).strip():
            for c in candidates:
                for p in c.get("provider_games", []):
                    if p.get("service") == "steam" and str(p.get("slug")) == steam_id:
                        return c

        if gog_id := str(game_data.get("gog_id", "")).strip():
            for c in candidates:
                for p in c.get("provider_games", []):
                    if p.get("service") == "gog" and str(p.get("slug")) == gog_id:
                        return c

        return max(
            candidates,
            key=lambda x: (
                len(x.get("provider_games", [])),
                len(x.get("platforms", [])),
                bool(x.get("coverart")),
                bool(x.get("background_image")),
            ),
        )

    def _get_lutris_data(self, game_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        search_order = [
            ("lutris_id", "lutris_id"),
            ("steam_id", "steamid"),
            ("gog_id", "gogid"),
            ("game_name", "search"),
        ]
        all_candidates = []
        for field, search_by in search_order:
            val = game_data.get(field)
            if not val:
                continue
            term = str(val).strip()
            if not term:
                continue

            if search_by == "lutris_id":
                if match := query_lutris_game_by_slug(term, session=self.session):
                    all_candidates.append(match)
            else:
                results = search_lutris_games(term, session=self.session)
                if search_by in {"steamid", "gogid"}:
                    service = search_by.replace("id", "")
                    for r in results:
                        for p in r.get("provider_games", []):
                            if p.get("service") == service and str(p.get("slug")) == term:
                                all_candidates.append(r)
                else:
                    lower_search = term.lower()
                    all_candidates.extend(r for r in results if r.get("name", "").strip().lower() == lower_search)

        return self._find_best_match(game_data, all_candidates) if all_candidates else None

    def _process_single_game(self, folder: str, game_data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        orig_providers: List[Dict[str, Any]] = []
        if game_data.get("steam_id"):
            orig_providers.append(
                {"name": game_data.get("game_name", ""), "service": "steam", "id": str(game_data["steam_id"])}
            )
        if game_data.get("gog_id"):
            orig_providers.append(
                {"name": game_data.get("game_name", ""), "service": "gog", "id": str(game_data["gog_id"])}
            )

        try:
            lutris_data = self._get_lutris_data(game_data)
        except Exception as e:
            logger.warning(f"Error enhancing data for {folder}, returning base data: {str(e)}")
            lutris_data = None

        processed = format_lutris_game_data(
            lutris_data,
            fallback_name=game_data.get("game_name", ""),
            original_providers=orig_providers,
        )
        if not lutris_data:
            processed["source"] = "Original"

        return folder, {
            "name": game_data.get("game_name", ""),
            "exe_path": game_data.get("exe_path", ""),
            "files": game_data.get("files", {}),
            "user_selected": False,
            **processed,
        }

    def enhance_with_lutris_data(self) -> Dict[str, Any]:
        enhanced_data = {}
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(self._process_single_game, folder, game_data): folder
                for folder, game_data in self.associate_data.items()
            }
            for future in as_completed(futures):
                folder_key = futures[future]
                try:
                    folder, result = future.result()
                    enhanced_data[folder] = result
                except Exception as e:
                    logger.error(f"Error processing game {folder_key}: {str(e)}")

        self.session.close()
        return enhanced_data


__all__ = [
    "LutrisDataEnhancer",
    "create_lutris_session",
    "format_lutris_game_data",
    "merge_providers",
    "query_lutris_game_by_slug",
    "search_lutris_games",
]
