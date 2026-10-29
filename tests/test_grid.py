"""Unit tests for Steam grid artwork downloading and fallback cascade."""

import unittest
from unittest.mock import patch, MagicMock
import tempfile
from pathlib import Path

from nosteam2steam.steam.grid import (
    search_steam_app_id,
    get_steam_images,
    get_gog_images,
    save_grid_images,
)


class TestGrid(unittest.TestCase):
    def test_get_steam_images(self):
        urls = get_steam_images("367520")
        self.assertIn("header", urls)
        self.assertIn("library_hero", urls)
        self.assertIn("logo", urls)
        self.assertIn("library_600x900", urls)
        self.assertEqual(urls["library_600x900"], "https://cdn.akamai.steamstatic.com/steam/apps/367520/library_600x900.jpg")

    @patch("requests.get")
    def test_get_gog_images(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "images": {
                "icon": "//images-1.gog-statics.com/icon.png",
                "background": "//images-1.gog-statics.com/bg.jpg",
                "logo": "//images-1.gog-statics.com/logo.png",
            }
        }
        mock_get.return_value = mock_resp

        gog_imgs = get_gog_images("1308320804")
        self.assertEqual(gog_imgs["icon"], "https://images-1.gog-statics.com/icon.png")
        self.assertEqual(gog_imgs["background"], "https://images-1.gog-statics.com/bg.jpg")
        self.assertEqual(gog_imgs["logo"], "https://images-1.gog-statics.com/logo.png")

    @patch("requests.get")
    def test_search_steam_app_id_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "total": 1,
            "items": [{"id": 367520, "name": "Hollow Knight"}]
        }
        mock_get.return_value = mock_resp

        appid = search_steam_app_id("Hollow Knight")
        self.assertEqual(appid, "367520")

    @patch("requests.get")
    def test_search_steam_app_id_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total": 0, "items": []}
        mock_get.return_value = mock_resp

        appid = search_steam_app_id("NonexistentGame123456")
        self.assertIsNone(appid)

    @patch("nosteam2steam.steam.grid.download_image")
    @patch("nosteam2steam.steam.grid.search_steam_app_id")
    def test_save_grid_images_steam_and_fallback(self, mock_search, mock_download):
        mock_search.return_value = "367520"

        # Simulate download_image returning True for all requests
        mock_download.return_value = True

        with tempfile.TemporaryDirectory() as tmp_dir:
            game_data = {
                "name": "Hollow Knight",
                "providers": [],
                "banner_url": "https://lutris.net/banner.jpg",
                "background_image": "https://lutris.net/bg.jpg",
                "coverart": "https://lutris.net/cover.jpg",
                "icon_url": "https://lutris.net/icon.png",
            }

            result = save_grid_images(
                app_id_short="12345678",
                user_config_dir=tmp_dir,
                game_data=game_data,
                bigpicture_appid="87654321",
                exe_path=None
            )

            # Check that files were assigned
            self.assertIn("header", result)
            self.assertIn("library_hero", result)
            self.assertIn("logo", result)
            self.assertIn("library_600x900", result)
            self.assertIn("icon", result)

            self.assertTrue(result["library_600x900"].endswith("12345678p.jpg"))
            self.assertTrue(result["library_hero"].endswith("12345678_hero.jpg"))
            self.assertTrue(result["logo"].endswith("12345678_logo.png"))
            self.assertTrue(result["header"].endswith("12345678.jpg"))
            self.assertTrue(result["icon"].endswith("12345678.png"))

    @patch("nosteam2steam.steam.grid.extract_icon")
    @patch("nosteam2steam.steam.grid.download_image")
    @patch("nosteam2steam.steam.grid.search_steam_app_id")
    def test_icon_emergency_fallback_to_exe(self, mock_search, mock_download, mock_extract):
        mock_search.return_value = None
        # Network download fails
        mock_download.return_value = False
        mock_extract.return_value = True

        with tempfile.TemporaryDirectory() as tmp_dir:
            dummy_exe = Path(tmp_dir) / "game.exe"
            dummy_exe.touch()

            game_data = {
                "name": "Local Game",
                "providers": [],
                "icon_url": "https://lutris.net/failed_icon.png",
            }

            result = save_grid_images(
                app_id_short="9999",
                user_config_dir=tmp_dir,
                game_data=game_data,
                exe_path=str(dummy_exe)
            )

            # extract_icon should have been called as fallback
            mock_extract.assert_called_once()
            self.assertIn("icon", result)
            self.assertTrue(result["icon"].endswith("9999.ico"))

    @patch("nosteam2steam.steam.grid.download_image")
    @patch("nosteam2steam.steam.grid.search_steam_app_id")
    def test_save_grid_images_fast_path_avoids_network(self, mock_search, mock_download):
        with tempfile.TemporaryDirectory() as tmp_dir:
            grid_dir = Path(tmp_dir) / "grid"
            icons_dir = Path(tmp_dir) / "icons"
            grid_dir.mkdir()
            icons_dir.mkdir()

            app_id = "5555"
            # Pre-create all images
            (grid_dir / f"{app_id}.jpg").write_bytes(b"header")
            (grid_dir / f"{app_id}_hero.jpg").write_bytes(b"hero")
            (grid_dir / f"{app_id}_logo.png").write_bytes(b"logo")
            (grid_dir / f"{app_id}p.jpg").write_bytes(b"poster")
            (icons_dir / f"{app_id}.ico").write_bytes(b"icon")

            game_data = {"name": "Cached Game", "providers": []}

            result = save_grid_images(
                app_id_short=app_id,
                user_config_dir=tmp_dir,
                game_data=game_data,
                exe_path=None,
            )

            # Assert fast path was taken without any network lookups or downloads
            mock_search.assert_not_called()
            mock_download.assert_not_called()
            self.assertEqual(len(result), 5)
            self.assertIn("icon", result)


if __name__ == "__main__":
    unittest.main()
