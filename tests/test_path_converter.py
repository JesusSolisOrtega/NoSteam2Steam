"""Unit tests for path conversion from Windows/PCGW to Linux/Proton."""

import tests.conftest  # noqa: F401
import unittest

from nosteam2steam.backup.path_converter import (
    PathConverter,
    transform_path_from_windows_to_proton,
)


class TestPathConverter(unittest.TestCase):
    def test_is_windows_game(self):
        self.assertTrue(PathConverter._is_windows_game({"exe_path": "/Games/Game/start.exe"}))
        self.assertTrue(PathConverter._is_windows_game({"exe_path": "/Games/Game/run.BAT"}))
        self.assertFalse(PathConverter._is_windows_game({"exe_path": "/Games/Game/start.sh"}))
        self.assertFalse(PathConverter._is_windows_game({}))

    def test_should_process_path_tags(self):
        # Save tag should be accepted
        self.assertTrue(PathConverter._should_process_path({}, ["save"]))
        # Config-only tag should be filtered out
        self.assertFalse(PathConverter._should_process_path({}, ["config"]))
        # Combined config + save tag should be accepted
        self.assertTrue(PathConverter._should_process_path({}, ["config", "save"]))

    def test_transform_path_win_app_data(self):
        game_data = {"app_id_short": "292030"}
        result = transform_path_from_windows_to_proton("<winAppData>/CDProjektRed/Witcher3", game_data)

        self.assertIn("292030", str(result))
        self.assertIn("users/steamuser/AppData/Roaming", str(result))
        self.assertIn("CDProjektRed/Witcher3", str(result))

    def test_transform_path_win_documents(self):
        game_data = {"app_id_short": "1086940"}
        result = transform_path_from_windows_to_proton("<winDocuments>/Larian Studios/Baldur's Gate 3", game_data)

        self.assertIn("1086940", str(result))
        self.assertIn("users/steamuser/Documents", str(result))

    def test_transform_path_base_fallback(self):
        game_data = {"app_id_short": "550", "exe_path": "/Games/Portal/portal.exe", "install_dir": "Portal"}
        result = transform_path_from_windows_to_proton("<base>/save", game_data)

        self.assertEqual(str(result), "/Games/Portal/save")

    def test_transform_path_root_expansion(self):
        from nosteam2steam.config import ROOT_PATH
        game_data = {"app_id_short": "550"}
        result = transform_path_from_windows_to_proton("<root>/userdata/12345/remote", game_data)

        self.assertTrue(str(result).startswith(str(ROOT_PATH)))
        self.assertNotIn("compatdata", str(result))

    def test_search_paths_case_insensitive(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a path with different casing on disk: lowercase "my games" and "game"
            pfx = Path(tmp_dir) / "12345" / "pfx" / "drive_c"
            save_dir = pfx / "users" / "steamuser" / "Documents" / "my games" / "indiegame"
            save_dir.mkdir(parents=True)
            save_file = save_dir / "slot1.sav"
            save_file.write_bytes(b"savedata")

            game_data = {
                "app_id_short": "12345",
                "files": {
                    "<winDocuments>/My Games/IndieGame/slot1.sav": {"tags": ["save"]}
                }
            }

            from unittest.mock import patch
            with patch("nosteam2steam.backup.path_converter.STEAMDECK_PATH", Path(tmp_dir)):
                results = PathConverter.search_paths("<winDocuments>/My Games/IndieGame/slot1.sav", game_data)
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["path"].resolve(), save_file.resolve())


if __name__ == "__main__":
    unittest.main()
