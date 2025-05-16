import requests
from typing import Dict, Any, Optional, List
from urllib.parse import quote
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("no_steam_to_steam.log")

class LutrisDataEnhancer:
    LUTRIS_API_URL = "https://lutris.net/api/games"
    REQUEST_TIMEOUT = 6
    MAX_RETRIES = 3
    BACKOFF_FACTOR = 1
    STATUS_FORCELIST = [500, 502, 503, 504]
    POOL_SCALING_FACTOR = 4

    def __init__(self, associate_data: Dict[str, Dict]):
        self.associate_data = associate_data
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        
        retry_strategy = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=self.BACKOFF_FACTOR,
            status_forcelist=self.STATUS_FORCELIST,
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=100,
            pool_maxsize=100,
            pool_block=False        
        )
        
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        session.headers.update({
            "Accept": "application/json",
            "User-Agent": "GameDataManager/1.0"
        })
        
        return session

    def _query_lutris_exact_match(self, search_term: str, search_by: str) -> Optional[Dict[str, Any]]:
        try:
            search_term = str(search_term).strip()
            if not search_term:
                logger.debug("Búsqueda con término vacío ignorada")
                return None

            if search_by == "lutris_id":
                url = f"{self.LUTRIS_API_URL}/{quote(search_term)}"
            else:
                url = f"{self.LUTRIS_API_URL}?search={quote(search_term)}"

            logger.debug(f"Consultando Lutris: {url}")
            response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()

            return data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug(f"No encontrado en Lutris: {search_term}")
            else:
                logger.warning(f"Error HTTP ({e.response.status_code}) al consultar Lutris: {e}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error de conexión al consultar Lutris: {e}")
        except Exception as e:
            logger.error(f"Error inesperado al consultar {search_term}: {str(e)}")

        return None

    def _find_best_match(self, game_data: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
            
        if len(candidates) == 1:
            return candidates[0]
            
        steam_id = game_data.get("steam_id")
        if steam_id:
            steam_id = str(steam_id).strip()
            for candidate in candidates:
                for provider in candidate.get("provider_games", []):
                    if provider.get("service") == "steam" and str(provider.get("slug")) == steam_id:
                        return candidate
                        
        gog_id = game_data.get("gog_id")
        if gog_id:
            gog_id = str(gog_id).strip()
            for candidate in candidates:
                for provider in candidate.get("provider_games", []):
                    if provider.get("service") == "gog" and str(provider.get("slug")) == gog_id:
                        return candidate
                        
        return max(candidates, key=lambda x: (
            len(x.get("provider_games", [])),
            len(x.get("platforms", [])),
            bool(x.get("coverart")),
            bool(x.get("background_image"))
        ))

    def _get_lutris_data(self, game_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:

        search_order = [
            ("lutris_id", "lutris_id"),
            ("steam_id", "steamid"),
            ("gog_id", "gogid"),
            ("game_name", "search")
        ]

        all_candidates = []
        
        for field, search_by in search_order:
            if game_data.get(field):
                search_term = str(game_data[field]).strip()
                response_data = self._query_lutris_exact_match(search_term, search_by)
                
                if search_by == "lutris_id":
                    if isinstance(response_data, dict):
                        all_candidates.append(response_data)
                else:
                    if isinstance(response_data, dict) and isinstance(response_data.get("results"), list):
                        if search_by in {"steamid", "gogid"}:
                            service = search_by.replace("id", "")
                            exact_matches = [
                                r for r in response_data["results"]
                                if any(
                                    p.get("service") == service and str(p.get("slug")) == search_term
                                    for p in r.get("provider_games", [])
                                )
                            ]
                        else:  
                            lower_search = search_term.lower()
                            exact_matches = [
                                r for r in response_data["results"]
                                if r.get("name", "").strip().lower() == lower_search
                            ]
                        
                        all_candidates.extend(exact_matches)
        
        return self._find_best_match(game_data, all_candidates) if all_candidates else None

    def _merge_providers(self, original_providers: List[Dict], lutris_providers: List[Dict]) -> List[Dict]:
        merged = []
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

    def _process_lutris_response(self, lutris_data: Dict[str, Any], game_data: Dict[str, Any]) -> Dict[str, Any]:
        if not lutris_data:
            return {}

        platforms = [p["name"] for p in lutris_data.get("platforms", []) if p.get("name")]
        
        lutris_providers = []
        for provider in lutris_data.get("provider_games", []):
            if not isinstance(provider, dict):
                continue
                
            service = provider.get("service", "").lower()
            if not service:
                continue
                
            lutris_providers.append({
                "name": provider.get("name", ""),
                "service": service,
                "id": provider.get("slug", "")
            })

        original_providers = []
        if game_data.get("steam_id"):
            original_providers.append({
                "name": game_data.get("game_name", ""),
                "service": "steam",
                "id": str(game_data["steam_id"])
            })
        if game_data.get("gog_id"):
            original_providers.append({
                "name": game_data.get("game_name", ""),
                "service": "gog",
                "id": str(game_data["gog_id"])
            })
        
        providers = self._merge_providers(original_providers, lutris_providers)

        return {
            "name": lutris_data.get("name", game_data.get("game_name", "")),
            "slug": lutris_data.get("slug", ""),
            "source": "Lutris",
            "platforms": platforms,
            "released": str(lutris_data.get("year", "")),
            "background_image": lutris_data.get("background_image", ""),
            "rating": str(lutris_data.get("rating", "")),
            "metacritic": str(lutris_data.get("metacritic", "")),
            "banner_url": lutris_data.get("banner_url", ""),
            "icon_url": lutris_data.get("icon_url", ""),
            "coverart": lutris_data.get("coverart", ""),
            "providers": providers
        }

    def _get_empty_response_structure(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        providers = []
        if game_data.get("steam_id"):
            providers.append({
                "name": game_data.get("game_name", ""),
                "service": "steam",
                "id": str(game_data["steam_id"])
            })
        if game_data.get("gog_id"):
            providers.append({
                "name": game_data.get("game_name", ""),
                "service": "gog",
                "id": str(game_data["gog_id"])
            })
        
        return {
            "name": game_data.get("game_name", ""),
            "slug": "",
            "source": "Original",
            "platforms": [],
            "released": "",
            "background_image": "",
            "rating": "",
            "metacritic": "",
            "banner_url": "",
            "icon_url": "",
            "coverart": "",
            "providers": providers
        }

    def _process_single_game(self, folder: str, game_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            lutris_data = self._get_lutris_data(game_data)
            processed_data = self._process_lutris_response(lutris_data, game_data)
        except Exception as e:
            logger.warning(f"Error al mejorar datos para {folder}, devolviendo datos base: {str(e)}")
            processed_data = self._get_empty_response_structure(game_data)
        
        return folder, {
            "name": game_data.get("game_name", ""),
            "exe_path": game_data.get("exe_path", ""),
            "files": game_data.get("files", {}),
            "user_selected": False,
            **processed_data
        }

    def enhance_with_lutris_data(self) -> Dict[str, Any]:
        enhanced_data = {}
        
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(self._process_single_game, folder, game_data): folder
                for folder, game_data in self.associate_data.items()
            }
            
            for future in as_completed(futures):
                try:
                    folder, result = future.result()
                    enhanced_data[folder] = result
                except Exception as e:
                    logger.error(f"Error procesando juego {folder}: {str(e)}")
        
        self.session.close()
        return enhanced_data
