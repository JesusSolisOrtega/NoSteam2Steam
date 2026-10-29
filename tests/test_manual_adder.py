"""Unit tests for manual game addition and heuristic name cleanup."""

import tempfile
import unittest
from unittest.mock import patch, MagicMock

from nosteam2steam.identification.heuristics import clean_executable_name as clean_from_heuristics
from nosteam2steam.identification.lutris import format_lutris_game_data
from nosteam2steam.identification.manual_adder import (
    clean_executable_name,
    manual_add_game,
    search_lutris_games,
)


class TestManualAdder(unittest.TestCase):
    def test_clean_executable_name_patterns(self):
        # Verify backwards-compatibility re-export as well as heuristics import
        self.assertEqual(clean_executable_name("/Games/HollowKnight/hollow_knight.exe"), "Hollow Knight")
        self.assertEqual(clean_from_heuristics("/Games/HollowKnight/hollow_knight.exe"), "Hollow Knight")

        # Case 2: CamelCase splitting
        self.assertEqual(clean_executable_name("/Games/Cyberpunk2077/Cyberpunk2077.exe"), "Cyberpunk2077")

        # Case 3: Launcher prefixes and architecture suffixes
        self.assertEqual(clean_executable_name("/Games/DeadCells/Launcher_DeadCells_x64.exe"), "Dead Cells")

        # Case 4: Generic executable name falling back to folder name
        self.assertEqual(clean_executable_name("/Games/Hades/Launcher.exe"), "Hades")
        self.assertEqual(clean_executable_name("/Games/Hades/Game.exe"), "Hades")
        self.assertEqual(clean_executable_name("/Games/Hades/Launcher_x64.exe"), "Hades")

        # Case 5: Executable in bin/subfolder falling back to root game folder
        self.assertEqual(clean_executable_name("/Games/Witcher3/bin/x64/witcher3.exe"), "Witcher3")
        self.assertEqual(clean_executable_name("/Games/Control/bin/shipping/Control.exe"), "Control")

    @patch("requests.get")
    def test_search_lutris_games(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "name": "Hollow Knight",
                    "slug": "hollow-knight",
                    "year": 2017,
                    "coverart": "http://example.com/cover.jpg",
                }
            ]
        }
        mock_get.return_value = mock_response

        results = search_lutris_games("hollow knight")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Hollow Knight")
        self.assertEqual(results[0]["year"], 2017)

    def test_format_lutris_game_data(self):
        # 1. With full Lutris data
        sample_lutris = {
            "name": "Celeste",
            "slug": "celeste",
            "year": 2018,
            "background_image": "http://example.com/bg.jpg",
            "coverart": "http://example.com/cover.jpg",
            "banner_url": "http://example.com/banner.jpg",
            "icon_url": "http://example.com/icon.png",
            "steamid": "504230",
            "provider_games": [{"service": "gog", "slug": "12345"}],
        }
        entry = format_lutris_game_data(sample_lutris, fallback_name="Celeste")
        self.assertEqual(entry["name"], "Celeste")
        self.assertEqual(entry["source"], "Lutris")
        self.assertEqual(entry["background_image"], "http://example.com/bg.jpg")
        provider_services = {p["service"] for p in entry["providers"]}
        self.assertIn("steam", provider_services)
        self.assertIn("gog", provider_services)

        # 2. Without Lutris data (fallback)
        fallback_entry = format_lutris_game_data(None, fallback_name="Custom Game")
        self.assertEqual(fallback_entry["name"], "Custom Game")
        self.assertEqual(fallback_entry["slug"], "custom-game")
        self.assertEqual(fallback_entry["source"], "Manual")
        self.assertEqual(fallback_entry["platforms"], ["PC"])

    @patch("nosteam2steam.identification.manual_adder.ui")
    @patch("nosteam2steam.identification.manual_adder.search_lutris_games")
    @patch("nosteam2steam.identification.manual_adder.ManifestRepository")
    def test_manual_add_game_full_flow(self, mock_repo_cls, mock_search, mock_ui):
        import os

        with tempfile.TemporaryDirectory() as tmp_dir:
            os.makedirs(f"{tmp_dir}/SubFolder", exist_ok=True)
            exe_path = f"{tmp_dir}/SubFolder/Game.exe"
            with open(exe_path, "w") as f:
                f.write("")

            mock_ui.select_path.return_value = exe_path
            mock_ui.show_entry.return_value = "SubFolder"
            mock_search.return_value = []
            mock_ui.ask_question.return_value = False

            mock_repo = MagicMock()
            mock_repo.get_by_name.return_value = {"files": {"saves": ["AppData/save.dat"]}}
            mock_repo_cls.return_value = mock_repo

            with patch("nosteam2steam.identification.manual_adder.DEFAULT_GAMES_INFO_PATH", f"{tmp_dir}/games.json"):
                success = manual_add_game()
                self.assertTrue(success)

                from nosteam2steam.identification.data_manager import GameDataManager

                dm = GameDataManager(f"{tmp_dir}/games.json")
                data = dm.get_current_data()
                self.assertIn("SubFolder", data)
                self.assertTrue(data["SubFolder"]["user_selected"])
                self.assertEqual(data["SubFolder"]["files"], {"saves": ["AppData/save.dat"]})

    def test_load_unmatched_candidates(self):
        import json
        from pathlib import Path
        from nosteam2steam.identification.manual_adder import load_unmatched_candidates

        with tempfile.TemporaryDirectory() as tmp_dir:
            cand_file = Path(tmp_dir) / "unmatched.json"
            real_exe = Path(tmp_dir) / "game.exe"
            real_exe.touch()

            cand_data = [
                {"folder_name": "GameA", "exe_path": str(real_exe)},
                {"folder_name": "GameB", "exe_path": str(Path(tmp_dir) / "nonexistent.exe")},
            ]
            cand_file.write_text(json.dumps(cand_data))

            with patch("nosteam2steam.identification.manual_adder.UNMATCHED_CANDIDATES_FILE", cand_file):
                loaded = load_unmatched_candidates()
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0]["folder_name"], "GameA")

    @patch("nosteam2steam.identification.manual_adder.ui")
    @patch("nosteam2steam.identification.manual_adder.search_lutris_games")
    @patch("nosteam2steam.identification.manual_adder.ManifestRepository")
    def test_manual_add_game_unmatched_cleanup(self, mock_repo_cls, mock_search, mock_ui):
        import json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            game_folder = Path(tmp_dir) / "MyGame"
            game_folder.mkdir()
            exe_path = str(game_folder / "game.exe")
            Path(exe_path).touch()

            cand_file = Path(tmp_dir) / "unmatched.json"
            cand_data = [
                {"folder_name": "MyGame", "exe_path": exe_path},
                {"folder_name": "OtherGame", "exe_path": "/some/other/game.exe"},
            ]
            cand_file.write_text(json.dumps(cand_data))

            # Menu choice '1' selects the candidate
            mock_ui.show_menu.side_effect = ["1", None]
            mock_ui.show_entry.return_value = "MyGame"
            mock_search.return_value = []
            mock_ui.ask_question.return_value = False

            mock_repo = MagicMock()
            mock_repo.get_by_name.return_value = None
            mock_repo.get_by_exe.return_value = None
            mock_repo_cls.return_value = mock_repo

            with patch("nosteam2steam.identification.manual_adder.DEFAULT_GAMES_INFO_PATH", f"{tmp_dir}/games.json"), \
                 patch("nosteam2steam.identification.manual_adder.UNMATCHED_CANDIDATES_FILE", cand_file):
                success = manual_add_game()
                self.assertTrue(success)

                # Verify cand_file removed MyGame
                remaining = json.loads(cand_file.read_text())
                self.assertEqual(len(remaining), 1)
                self.assertEqual(remaining[0]["folder_name"], "OtherGame")



if __name__ == "__main__":
    unittest.main()
