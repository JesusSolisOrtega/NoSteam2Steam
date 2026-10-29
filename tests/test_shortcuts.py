"""Unit tests for Steam shortcuts.vdf binary manipulation."""

import unittest
import tempfile
import os

from nosteam2steam.steam.shortcuts import (
    load_shortcuts,
    save_shortcuts,
    reindex_shortcuts_alphabetically,
    game_exists,
    find_entry_index,
)


class TestShortcuts(unittest.TestCase):
    def setUp(self):
        self.sample_shortcuts = {
            "0": {
                "appid": -12345678,
                "appname": "Zelda",
                "Exe": '"/path/to/zelda.exe"',
                "StartDir": '"/path/to/"',
                "icon": "",
                "ShortcutPath": "",
                "LaunchOptions": "",
                "IsHidden": 0,
                "AllowDesktopConfig": 1,
                "AllowOverlay": 1,
                "OpenVR": 0,
                "Devkit": 0,
                "DevkitGameID": "",
                "DevkitOverrideAppID": 0,
                "LastPlayTime": 0,
                "FlatpakAppID": "",
                "tags": {},
            },
            "1": {
                "appid": -87654321,
                "appname": "Apex",
                "Exe": '"/path/to/apex.exe"',
                "StartDir": '"/path/to/"',
                "icon": "",
                "ShortcutPath": "",
                "LaunchOptions": "",
                "IsHidden": 0,
                "AllowDesktopConfig": 1,
                "AllowOverlay": 1,
                "OpenVR": 0,
                "Devkit": 0,
                "DevkitGameID": "",
                "DevkitOverrideAppID": 0,
                "LastPlayTime": 0,
                "FlatpakAppID": "",
                "tags": {},
            },
        }

    def test_binary_vdf_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix=".vdf", delete=False) as f:
            temp_path = f.name

        try:
            save_shortcuts(temp_path, self.sample_shortcuts)
            loaded = load_shortcuts(temp_path)

            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded["0"]["appname"], "Zelda")
            self.assertEqual(loaded["1"]["appname"], "Apex")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_reindex_shortcuts_alphabetically(self):
        reindexed = reindex_shortcuts_alphabetically(self.sample_shortcuts)
        # Apex should be first (index "0"), Zelda second (index "1")
        self.assertEqual(reindexed["0"]["appname"], "Apex")
        self.assertEqual(reindexed["1"]["appname"], "Zelda")

    def test_find_entry_index(self):
        next_str_idx, next_int_idx = find_entry_index(self.sample_shortcuts)
        self.assertEqual(next_str_idx, "2")
        self.assertEqual(next_int_idx, 2)

    def test_game_exists(self):
        with tempfile.NamedTemporaryFile(suffix=".vdf", delete=False) as f:
            temp_path = f.name

        try:
            save_shortcuts(temp_path, self.sample_shortcuts)

            # Check existing game by Exe and AppName from file path
            self.assertTrue(game_exists(temp_path, "/path/to/zelda.exe", "Zelda"))
            # Non-existent game from file path
            self.assertFalse(game_exists(temp_path, "/path/to/other.exe", "Other"))

            # Check directly from in-memory dictionary
            self.assertTrue(game_exists(self.sample_shortcuts, "/path/to/zelda.exe", "Zelda"))
            self.assertFalse(game_exists(self.sample_shortcuts, "/path/to/other.exe", "Other"))
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
