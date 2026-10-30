"""Unit tests for XDG Desktop Entry creation and removal."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from nosteam2steam.desktop import (
    get_desktop_dir,
    get_desktop_entry_content,
    get_persistent_icon_path,
    install_desktop_entry,
    is_desktop_entry_installed,
    manage_desktop_shortcut,
    uninstall_desktop_entry,
)


class TestDesktopIntegration(unittest.TestCase):
    def test_get_desktop_entry_content(self):
        content = get_desktop_entry_content("/usr/bin/launch.sh", "/usr/share/icon.png", "/usr/bin")
        self.assertIn("[Desktop Entry]", content)
        self.assertIn("Name=NoSteam2Steam", content)
        self.assertIn("Exec=/usr/bin/launch.sh", content)
        self.assertIn("Icon=/usr/share/icon.png", content)
        self.assertIn("Path=/usr/bin", content)
        self.assertIn("Categories=Game;Utility;", content)
        self.assertIn("StartupNotify=true", content)

    def test_get_persistent_icon_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = Path(tmp_dir)
            with patch("pathlib.Path.home", return_value=fake_home):
                p = get_persistent_icon_path()
                self.assertTrue(Path(p).name.endswith("icon.png"))

    def test_install_and_uninstall_desktop_entry(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = Path(tmp_dir)
            (fake_home / "Desktop").mkdir(parents=True)
            (fake_home / ".local/share/applications").mkdir(parents=True)

            with patch("pathlib.Path.home", return_value=fake_home):
                success = install_desktop_entry(target_desktop=True, target_menu=True)
                self.assertTrue(success)

                menu_entry = fake_home / ".local/share/applications/nosteam2steam.desktop"
                desktop_entry = fake_home / "Desktop/nosteam2steam.desktop"

                self.assertTrue(menu_entry.exists())
                self.assertTrue(desktop_entry.exists())
                self.assertIn("NoSteam2Steam", menu_entry.read_text())

                # Test uninstall
                del_success = uninstall_desktop_entry()
                self.assertTrue(del_success)
                self.assertFalse(menu_entry.exists())
                self.assertFalse(desktop_entry.exists())

    def test_install_desktop_entry_frozen_mode(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = Path(tmp_dir)
            (fake_home / "Desktop").mkdir(parents=True)
            (fake_home / ".local/share/applications").mkdir(parents=True)

            fake_bin = fake_home / "Games" / "noSteam2Steam.bin"
            fake_bin.parent.mkdir(parents=True, exist_ok=True)
            fake_bin.touch()

            with patch("pathlib.Path.home", return_value=fake_home), \
                 patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "executable", str(fake_bin)):
                success = install_desktop_entry(target_desktop=True, target_menu=True)
                self.assertTrue(success)

                desktop_entry = fake_home / "Desktop/nosteam2steam.desktop"
                self.assertTrue(desktop_entry.exists())
                content = desktop_entry.read_text()
                # Must reference the standalone binary directly without python script parameters
                self.assertIn(f'Exec="{fake_bin}"', content)
                self.assertNotIn("noSteam2Steam.py", content)
                self.assertIn(f'Path={fake_bin.parent}', content)

    def test_get_desktop_dir_fallback_and_xdg(self):
        from unittest.mock import Mock

        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = Path(tmp_dir)
            fake_escritorio = fake_home / "Escritorio"
            fake_escritorio.mkdir()

            with patch("pathlib.Path.home", return_value=fake_home):
                with patch("subprocess.run") as mock_run:
                    # Case 1: xdg-user-dir returns Escritorio
                    mock_run.return_value = Mock(returncode=0, stdout=str(fake_escritorio) + "\n")
                    d = get_desktop_dir()
                    self.assertEqual(d, fake_escritorio)

                    # Case 2: xdg-user-dir fails, falls back to existing Escritorio directory
                    mock_run.return_value = Mock(returncode=1, stdout="")
                    d_fallback = get_desktop_dir()
                    self.assertEqual(d_fallback, fake_escritorio)

    def test_manage_desktop_shortcut_flow(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = Path(tmp_dir)
            (fake_home / "Desktop").mkdir(parents=True)
            (fake_home / ".local/share/applications").mkdir(parents=True)

            with patch("pathlib.Path.home", return_value=fake_home), \
                 patch("nosteam2steam.desktop.ui.ask_question") as mock_ask, \
                 patch("nosteam2steam.desktop.ui.show_info"):

                # 1. User confirms activation
                mock_ask.return_value = True
                self.assertFalse(is_desktop_entry_installed())
                success = manage_desktop_shortcut()
                self.assertTrue(success)
                self.assertTrue(is_desktop_entry_installed())

                # 2. User confirms deactivation
                mock_ask.return_value = True
                success_deact = manage_desktop_shortcut()
                self.assertTrue(success_deact)
                self.assertFalse(is_desktop_entry_installed())

                # 3. User cancels
                mock_ask.return_value = False
                success_cancel = manage_desktop_shortcut()
                self.assertFalse(success_cancel)


if __name__ == "__main__":
    unittest.main()
