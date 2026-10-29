"""Tests specifically validating portability and behavior on Steam Deck / SteamOS."""

import unittest
import tempfile
import os
import shutil
from pathlib import Path
from unittest.mock import patch

from nosteam2steam.config import (
    get_latest_proton_ge,
    get_latest_proton,
    get_proton_version,
    get_current_user,
    generate_app_id,
    generate_short_app_id,
)
from nosteam2steam.identification.manual_adder import clean_executable_name
from nosteam2steam.backup.path_converter import transform_path_from_windows_to_proton


class TestSteamOSCompatibility(unittest.TestCase):
    def test_no_hardcoded_developer_paths_in_package(self):
        """Verify that developer-specific host paths are not hardcoded in the codebase."""
        package_root = Path(__file__).resolve().parent.parent / "nosteam2steam"
        developer_markers = ["/home/jesus", "C:\\", "D:\\"]

        violations = []
        for py_file in package_root.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for marker in developer_markers:
                if marker in content:
                    violations.append(f"{py_file.name} contains '{marker}'")

        self.assertEqual(violations, [], f"Developer-specific paths detected: {violations}")

    def test_proton_ge_numeric_version_sorting(self):
        """Ensure GE-Proton10-1 is correctly ranked higher than GE-Proton9-25."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tools_dir = Path(tmp_dir) / "compatibilitytools.d"
            tools_dir.mkdir(parents=True)

            # Create dummy GE-Proton folders
            (tools_dir / "GE-Proton7-55").mkdir()
            (tools_dir / "GE-Proton9-25").mkdir()
            (tools_dir / "GE-Proton10-1").mkdir()
            (tools_dir / "GE-Proton8-26").mkdir()

            with patch("nosteam2steam.config.PROTON_GE_DIRS", [str(tools_dir)]):
                selected = get_latest_proton_ge()
                self.assertEqual(
                    selected, "GE-Proton10-1", "GE-Proton version comparison must be numeric, not lexicographical."
                )
                self.assertEqual(get_proton_version(), "GE-Proton10-1")

    def test_proton_official_version_sorting_and_experimental_fallback(self):
        """Ensure Proton Experimental is prioritized, and falls back to latest numbered Proton (e.g. 9.0 > 8.0)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            common_dir = Path(tmp_dir) / "steamapps" / "common"
            common_dir.mkdir(parents=True)

            (common_dir / "Proton 7.0").mkdir()
            (common_dir / "Proton 8.0").mkdir()
            (common_dir / "Proton 9.0").mkdir()
            (common_dir / "Proton Experimental").mkdir()

            with patch("nosteam2steam.config.PROTON_DIRS", [str(common_dir)]):
                selected = get_latest_proton()
                self.assertEqual(selected, "Proton Experimental")

            # Remove Experimental to test fallback to highest numbered Proton
            shutil.rmtree(common_dir / "Proton Experimental")

            with patch("nosteam2steam.config.PROTON_DIRS", [str(common_dir)]):
                selected = get_latest_proton()
                self.assertEqual(selected, "Proton 9.0")

            # Remove Proton 9.0 to ensure 8.0 is selected next
            shutil.rmtree(common_dir / "Proton 9.0")

            with patch("nosteam2steam.config.PROTON_DIRS", [str(common_dir)]):
                selected = get_latest_proton()
                self.assertEqual(selected, "Proton 8.0")

    def test_get_current_user_with_steamdeck_loginusers(self):
        """Simulate SteamOS loginusers.vdf with Steam Deck 64-bit ID."""
        mock_vdf_content = """
        "users"
        {
            "76561198012345678"
            {
                "AccountName" "deck_user"
                "PersonaName" "DeckPlayer"
                "MostRecent" "1"
                "Timestamp" "1700000000"
            }
            "76561198087654321"
            {
                "AccountName" "secondary_user"
                "PersonaName" "Secondary"
                "MostRecent" "0"
                "Timestamp" "1600000000"
            }
        }
        """
        with tempfile.NamedTemporaryFile("w", suffix=".vdf", delete=False) as f:
            f.write(mock_vdf_content)
            tmp_path = f.name

        try:
            with patch("nosteam2steam.config.LOGINUSERS_PATHS", [tmp_path]):
                current_user = get_current_user()
                # 76561198012345678 - 76561197960265728 = 52079950
                self.assertEqual(current_user, "52079950")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_microsd_path_handling(self):
        """Verify handling of typical Steam Deck MicroSD mount points."""
        sd_paths = [
            "/run/media/mmcblk0p1/Games/HollowKnight/hollow_knight.exe",
            "/run/media/deck/ABCD-1234/Games/EldenRing/eldenring.exe",
        ]

        for exe_path in sd_paths:
            # Name cleanup should work normally with MicroSD paths
            cleaned = clean_executable_name(exe_path)
            self.assertNotIn("/run/media", cleaned)
            self.assertTrue(len(cleaned) > 0)

            # App ID generation should be deterministic on MicroSD paths
            app_id = generate_app_id(f'"{exe_path}"', cleaned)
            short_id = generate_short_app_id(f'"{exe_path}"', cleaned)
            self.assertTrue(app_id.isdigit())
            self.assertTrue(short_id.isdigit())

            # Path conversion for save games should map to the correct compatdata prefix
            game_data = {"app_id_short": short_id, "exe_path": exe_path}
            proton_path = transform_path_from_windows_to_proton("<winAppData>/saves", game_data)
            self.assertIn(short_id, str(proton_path))
            self.assertIn("AppData/Roaming/saves", str(proton_path))

    def test_steamos_microsd_auto_discovery(self):
        """Verify that get_default_sync_folders finds Steam Deck SD card directories."""
        from nosteam2steam.identification.folders import get_default_sync_folders

        orig_exists = os.path.exists
        orig_isdir = os.path.isdir

        def mock_exists(p):
            if p in ("/run/media/mmcblk0p1", "/run/media/mmcblk0p1/Games"):
                return True
            return orig_exists(p)

        def mock_isdir(p):
            if p == "/run/media/mmcblk0p1/Games":
                return True
            return orig_isdir(p)

        with patch("os.path.exists", side_effect=mock_exists):
            with patch("os.path.isdir", side_effect=mock_isdir):
                defaults = get_default_sync_folders()
                self.assertIn("/run/media/mmcblk0p1/Games", defaults)

    def test_gamemode_detection(self):
        """Verify that is_steamdeck_gamemode correctly flags gamescope sessions."""
        from nosteam2steam.utils import is_steamdeck_gamemode

        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "gamescope"}):
            self.assertTrue(is_steamdeck_gamemode())

        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}):
            self.assertFalse(is_steamdeck_gamemode())


if __name__ == "__main__":
    unittest.main()
