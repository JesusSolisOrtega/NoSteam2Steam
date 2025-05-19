import json
from pathlib import Path
from typing import Dict, Any
import logging
import threading
import time
from identify_game import run_identification
from lutris_search_enhancement import LutrisDataEnhancer


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("no_steam_to_steam.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("no_steam_to_steam.log")

class GameDataManager:
    def __init__(self, json_path: str = "games.json"):
        self.json_path = Path(json_path)
        self.data = self._load_existing_data()
        self.lock = threading.Lock()

    def _load_existing_data(self) -> Dict[str, Any]:
        if self.json_path.exists():
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading file {self.json_path}: {str(e)}")
                return {}
        return {}

    def _merge_game_data(self, existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        if not existing:
            return new.copy()
        if not new:
            return existing.copy()
        
        merged = existing.copy()
        
        simple_fields = ['name', 'slug', 'source', 'released', 'background_image', 
                        'rating', 'metacritic', 'banner_url', 'icon_url', 'coverart', 'exe_path',
                        'user_selected']
        for field in simple_fields:
            if field in new and (field not in merged or not merged[field]):
                merged[field] = new[field]
        
        if 'platforms' in new:
            existing_platforms = set(existing.get('platforms', []))
            new_platforms = set(new.get('platforms', []))
            merged['platforms'] = list(existing_platforms.union(new_platforms))
        
        if 'providers' in new:
            existing_providers = {tuple(sorted(d.items())) for d in existing.get('providers', [])}
            new_providers = {tuple(sorted(d.items())) for d in new.get('providers', [])}
            merged['providers'] = [dict(p) for p in existing_providers.union(new_providers)]
        
        return merged

    def update_data(self, new_data: Dict[str, Dict[str, Any]]) -> None:
        with self.lock:
            for game_key, game_data in new_data.items():
                if game_key in self.data:
                    self.data[game_key] = self._merge_game_data(self.data[game_key], game_data)
                else:
                    self.data[game_key] = game_data

    def save_data(self) -> None:
        temp_path = self.json_path.with_suffix('.tmp')
        
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            
            temp_path.replace(self.json_path)
            logger.info(f"Data successfully saved to {self.json_path}")
        except IOError as e:
            logger.error(f"Error saving data: {str(e)}")
            if temp_path.exists():
                temp_path.unlink()

    def get_current_data(self) -> Dict[str, Any]:
        with self.lock:
            return self.data.copy()


def main():
    start_time = time.time()
    
    logger.info("Retrieving initial data...")
    associate_data = run_identification()
    
    logger.info("Enhancing data with Lutris information...")
    enhancer = LutrisDataEnhancer(associate_data)
    enhanced_data = enhancer.enhance_with_lutris_data()
    
    logger.info("Updating database...")
    manager = GameDataManager()
    manager.update_data(enhanced_data)
    manager.save_data()
    
    elapsed = time.time() - start_time
    logger.info(f"Process completed in {elapsed:.2f} seconds")
    logger.info(f"Total games processed: {len(enhanced_data)}")

if __name__ == "__main__":
    main()
