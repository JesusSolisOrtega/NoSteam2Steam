"""Unit tests for configuration, path resolution, and ID generation."""

import unittest
import os
from pathlib import Path
from unittest.mock import patch

from nosteam2steam.config import (
    generate_app_id,
    generate_short_app_id,
    generate_shortcut_id,
    steamid64_to_accountid,
    accountid_to_steamid64,
    get_noSteam2Steam_dir,
    STEAMID64_BASE,
)


class TestConfig(unittest.TestCase):
    def test_app_id_generation_consistency(self):
        exe = '"/home/deck/Games/Hades/Hades.exe"'
        app_name = "Hades"

        id1 = generate_app_id(exe, app_name)
        id2 = generate_app_id(exe, app_name)
        self.assertEqual(id1, id2, "App ID generation must be deterministic.")

        short_id1 = generate_short_app_id(exe, app_name)
        short_id2 = generate_short_app_id(exe, app_name)
        self.assertEqual(short_id1, short_id2, "Short App ID generation must be deterministic.")

        shortcut_id = generate_shortcut_id(exe, app_name)
        self.assertIsInstance(shortcut_id, int)

        # App IDs must be non-empty numeric strings
        self.assertTrue(id1.isdigit())
        self.assertTrue(short_id1.isdigit())

    def test_steamid_conversions(self):
        account_id = "12345678"
        steamid64 = accountid_to_steamid64(account_id)
        self.assertEqual(steamid64, int(account_id) + STEAMID64_BASE)

        recovered_acc_id = steamid64_to_accountid(steamid64)
        self.assertEqual(recovered_acc_id, int(account_id))

    def test_get_nosteam2steam_dir_fallback(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/tmp/test_xdg_data"}):
            dir_path = get_noSteam2Steam_dir()
            self.assertIsInstance(dir_path, Path)
            self.assertTrue(str(dir_path).endswith("noSteam2Steam"))

    def test_cli_argument_parsing(self):
        from nosteam2steam.app import parse_arguments

        args = parse_arguments(["--sync"])
        self.assertTrue(args.sync)
        self.assertFalse(args.add_games)

        args = parse_arguments(["--add-games", "--quiet"])
        self.assertTrue(args.add_games)
        self.assertTrue(args.quiet)

        args = parse_arguments(["--sync-saves"])
        self.assertTrue(args.sync_saves)

        args = parse_arguments(["--clean-config"])
        self.assertTrue(args.clean_config)


if __name__ == "__main__":
    unittest.main()
