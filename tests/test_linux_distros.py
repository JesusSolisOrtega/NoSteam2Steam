"""Tests validating multi-distribution Linux portability, package formats, and cross-library save management."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nosteam2steam.config import (
    get_all_compatdata_dirs,
    get_steam_library_folders,
    get_steam_root,
)
from nosteam2steam.backup.path_converter import (
    PathConverter,
    transform_path_from_windows_to_proton,
)
from nosteam2steam.identification.folders import get_default_sync_folders
from nosteam2steam.services import get_syncthing_service_name


class TestLinuxDistrosCompatibility(unittest.TestCase):
    def test_steam_root_environment_override(self):
        """Verify that STEAM_DIR / STEAM_ROOT overrides default paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_dir = Path(tmp_dir) / "custom_steam"
            custom_dir.mkdir()
            with patch.dict(os.environ, {"STEAM_DIR": str(custom_dir)}):
                detected = get_steam_root()
                self.assertEqual(detected, custom_dir)

    def test_flatpak_steam_root_detection(self):
        """Verify discovery of Flatpak Steam installation (com.valvesoftware.Steam)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = Path(tmp_dir)
            flatpak_steam = fake_home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"
            (flatpak_steam / "steamapps").mkdir(parents=True)

            with patch("pathlib.Path.home", return_value=fake_home):
                with patch.dict(os.environ, {}, clear=True):
                    detected = get_steam_root()
                    self.assertEqual(detected, flatpak_steam)

    def test_snap_steam_root_detection(self):
        """Verify discovery of Snap Steam installation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = Path(tmp_dir)
            snap_steam = fake_home / "snap/steam/common/.local/share/Steam"
            (snap_steam / "steamapps").mkdir(parents=True)

            with patch("pathlib.Path.home", return_value=fake_home):
                with patch.dict(os.environ, {}, clear=True):
                    detected = get_steam_root()
                    self.assertEqual(detected, snap_steam)

    def test_multi_library_parsing_and_compatdata_discovery(self):
        """Verify parsing of libraryfolders.vdf across secondary storage drives."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "Steam"
            steamapps = root / "steamapps"
            steamapps.mkdir(parents=True)

            # Secondary drive library
            secondary_lib = Path(tmp_dir) / "SecondaryDrive/SteamLibrary"
            (secondary_lib / "steamapps/compatdata").mkdir(parents=True)

            vdf_content = f'''
            "libraryfolders"
            {{
                "0"
                {{
                    "path"    "{str(root)}"
                }}
                "1"
                {{
                    "path"    "{str(secondary_lib)}"
                }}
            }}
            '''
            (steamapps / "libraryfolders.vdf").write_text(vdf_content, encoding="utf-8")

            libraries = get_steam_library_folders(root)
            self.assertEqual(len(libraries), 2)
            self.assertIn(secondary_lib, libraries)

            # Compatdata discovery across all libraries
            compat_dirs = get_all_compatdata_dirs(root)
            self.assertIn(secondary_lib / "steamapps/compatdata", compat_dirs)

    def test_save_game_resolution_in_secondary_library_compatdata(self):
        """Ensure save game paths resolve correctly when game prefix is located in secondary library."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            secondary_compat = Path(tmp_dir) / "mnt/games/SteamLibrary/steamapps/compatdata"
            prefix_drive_c = secondary_compat / "123456" / "pfx" / "drive_c"
            save_folder = prefix_drive_c / "users/steamuser/AppData/Roaming/MyGame"
            save_folder.mkdir(parents=True)
            (save_folder / "save.dat").write_text("savedata")

            with patch("nosteam2steam.config.get_all_compatdata_dirs", return_value=[secondary_compat]):
                resolved_prefix = PathConverter.get_proton_path("123456")
                self.assertEqual(resolved_prefix, prefix_drive_c)

                game_data = {"app_id_short": "123456", "exe_path": "/mnt/games/MyGame/game.exe"}
                transformed = transform_path_from_windows_to_proton("<winAppData>/MyGame/save.dat", game_data)
                self.assertTrue(str(transformed).endswith("users/steamuser/AppData/Roaming/MyGame/save.dat"))

    def test_linux_native_save_path_expansion(self):
        """Verify expansion of Linux native save path variables (<xdgDataHome>, <xdgConfigHome>)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = Path(tmp_dir)
            with patch("pathlib.Path.home", return_value=fake_home):
                game_data = {
                    "app_id_short": "9999",
                    "exe_path": f"{tmp_dir}/NativeGame/game.x86_64",
                    "install_dir": "NativeGame",
                }
                paths = PathConverter.expand_path("<xdgDataHome>/NativeGame/saves", game_data, system="linux")
                self.assertTrue(len(paths) > 0)
                self.assertIn(".local/share/NativeGame/saves", str(paths[0]["physical_path"]))

    def test_debian_ubuntu_and_arch_mount_auto_discovery(self):
        """Verify auto-discovery of mounts under /media/<user> (Debian/Ubuntu) and /run/media/<user> (Arch/Fedora)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Simulate Debian /media/username/USB_GAMES/Games
            media_dir = Path(tmp_dir) / "media"
            usb_games = media_dir / "user1" / "USB_GAMES" / "Games"
            usb_games.mkdir(parents=True)

            # Simulate Fedora /run/media/username/External/Games
            run_media_dir = Path(tmp_dir) / "run_media"
            ext_games = run_media_dir / "user1" / "External" / "Games"
            ext_games.mkdir(parents=True)

            # Simulate /mnt/Games
            mnt_dir = Path(tmp_dir) / "mnt"
            mnt_games = mnt_dir / "Games"
            mnt_games.mkdir(parents=True)

            orig_exists = os.path.exists
            orig_isdir = os.path.isdir
            orig_listdir = os.listdir

            def fake_exists(p):
                s = str(p)
                if s in ("/media", "/run/media", "/mnt"):
                    return True
                if "/media" in s or "/run/media" in s or "/mnt" in s:
                    return orig_exists(s.replace("/media", str(media_dir)).replace("/run/media", str(run_media_dir)).replace("/mnt", str(mnt_dir)))
                return orig_exists(p)

            def fake_isdir(p):
                s = str(p)
                if "/media" in s or "/run/media" in s or "/mnt" in s:
                    return orig_isdir(s.replace("/media", str(media_dir)).replace("/run/media", str(run_media_dir)).replace("/mnt", str(mnt_dir)))
                return orig_isdir(p)

            def fake_listdir(p):
                s = str(p)
                if "/media" in s or "/run/media" in s or "/mnt" in s:
                    return orig_listdir(s.replace("/media", str(media_dir)).replace("/run/media", str(run_media_dir)).replace("/mnt", str(mnt_dir)))
                return orig_listdir(p)

            with patch("os.path.exists", side_effect=fake_exists), \
                 patch("os.path.isdir", side_effect=fake_isdir), \
                 patch("os.listdir", side_effect=fake_listdir):
                folders = get_default_sync_folders()
                found = any("USB_GAMES/Games" in f for f in folders) or any("External/Games" in f for f in folders)
                self.assertTrue(found)

    def test_syncthing_service_detection(self):
        """Verify standard Linux syncthing.service vs SteamOS syncthingy.service detection."""
        with patch("nosteam2steam.services.is_service_active") as mock_active:
            # Case 1: Standard Linux has syncthing.service active
            mock_active.side_effect = lambda s: s == "syncthing.service"
            self.assertEqual(get_syncthing_service_name(), "syncthing.service")

            # Case 2: SteamOS has syncthingy.service active
            mock_active.side_effect = lambda s: s == "syncthingy.service"
            self.assertEqual(get_syncthing_service_name(), "syncthingy.service")


if __name__ == "__main__":
    unittest.main()
