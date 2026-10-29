"""Unit tests for XDG Desktop Entry creation and removal."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nosteam2steam.desktop import (
    get_desktop_entry_content,
    install_desktop_entry,
    uninstall_desktop_entry,
)


class TestDesktopIntegration(unittest.TestCase):
    def test_get_desktop_entry_content(self):
        content = get_desktop_entry_content("/usr/bin/launch.sh", "/usr/share/icon.png")
        self.assertIn("[Desktop Entry]", content)
        self.assertIn("Name=NoSteam2Steam", content)
        self.assertIn("Exec=/usr/bin/launch.sh", content)
        self.assertIn("Icon=/usr/share/icon.png", content)
        self.assertIn("Categories=Game;Utility;", content)
        self.assertIn("StartupNotify=true", content)

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


if __name__ == "__main__":
    unittest.main()

