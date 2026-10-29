"""Unit tests for atomic game identification components."""

import tempfile
from pathlib import Path
import unittest

from nosteam2steam.identification.candidates import CandidateResolver
from nosteam2steam.identification.data_manager import GameDataManager
from nosteam2steam.identification.manifests import ManifestRepository
from nosteam2steam.identification.matcher import GameMatcher
from nosteam2steam.identification.platform import PlatformResolver


class TestIdentificationComponents(unittest.TestCase):
    def setUp(self):
        self.mock_indexes = {
            "xml": {"deadcells": "Dead Cells", "hades": "Hades"},
            "yaml": {
                "_metadata": [
                    {
                        "game_name": "Dead Cells",
                        "steam_id": "588650",
                        "gog_id": "1940986061",
                        "lutris_id": "dead-cells",
                        "files": {},
                    },
                    {
                        "game_name": "Hades",
                        "steam_id": "1145360",
                        "gog_id": "1440782390",
                        "lutris_id": "hades",
                        "files": {},
                    },
                ],
                "by_exe": {"deadcells.exe": 0, "hades.exe": 1},
                "by_path": {"dead cells/deadcells.exe": 0, "hades/hades.exe": 1},
                "by_install_dir": {
                    "dead cells": {"_meta": 0, "launch": {"deadcells.exe": []}},
                    "hades": {"_meta": 1, "launch": {"hades.exe": []}},
                },
                "by_steam_id": {"588650": 0, "1145360": 1},
                "by_gog_id": {"1940986061": 0, "1440782390": 1},
                "by_name": {"dead cells": 0, "hades": 1},
                "by_name_fuzzy": {"dead": [0], "cells": [0], "hades": [1]},
            },
        }
        self.repo = ManifestRepository(preloaded=self.mock_indexes)

    def test_manifest_repository_lookups(self):
        steam_entry = self.repo.get_by_steam_id("588650")
        assert steam_entry is not None
        self.assertEqual(steam_entry["game_name"], "Dead Cells")

        gog_entry = self.repo.get_by_gog_id("1440782390")
        assert gog_entry is not None
        self.assertEqual(gog_entry["game_name"], "Hades")

        exe_entry = self.repo.get_by_exe("deadcells.exe")
        assert exe_entry is not None
        self.assertEqual(exe_entry["game_name"], "Dead Cells")

        self.assertEqual(self.repo.get_xml_game_name("deadcells"), "Dead Cells")
        self.assertEqual(len(self.repo.get_fuzzy_matches("hades")), 1)

        # Backward compatibility interface
        self.assertEqual(self.repo["xml"]["deadcells"], "Dead Cells")
        self.assertIn("deadcells.exe", self.repo["yaml_by_exe"])
        yaml_steam = self.repo.get("yaml_by_steam_id")
        assert yaml_steam is not None
        self.assertEqual(yaml_steam["588650"]["game_name"], "Dead Cells")

    def test_platform_detector_and_resolver(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            game_dir = Path(tmp_dir) / "Hades"
            game_dir.mkdir()
            (game_dir / "steam_appid.txt").write_text("1145360", encoding="utf-8")
            (game_dir / "Hades.exe").write_bytes(b"mock_binary")

            resolver = PlatformResolver(repository=self.repo)
            match = resolver.resolve("Hades", str(game_dir))

            self.assertIsNotNone(match)
            assert match is not None
            self.assertEqual(match["steam_id"], "1145360")
            self.assertEqual(match["game_name"], "Hades")
            self.assertTrue(match["exe_path"].endswith("Hades.exe"))

    def test_candidate_resolver_direct_yaml(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sync_dir = Path(tmp_dir)
            game_dir = sync_dir / "Dead Cells"
            game_dir.mkdir()
            exe_file = game_dir / "deadcells.exe"
            exe_file.write_bytes(b"mock_binary")

            resolver = CandidateResolver(repository=self.repo, sync_folder=str(sync_dir))
            match = resolver.resolve("Dead Cells", str(game_dir))

            self.assertIsNotNone(match)
            assert match is not None
            self.assertEqual(match["game_name"], "Dead Cells")
            self.assertEqual(match["steam_id"], "588650")

    def test_candidate_resolver_fuzzy(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sync_dir = Path(tmp_dir)
            game_dir = sync_dir / "Hades Game Folder"
            game_dir.mkdir()
            exe_file = game_dir / "Hades.exe"
            exe_file.write_bytes(b"mock_binary")

            resolver = CandidateResolver(repository=self.repo, sync_folder=str(sync_dir))
            match = resolver.resolve("Hades Game Folder", str(game_dir))

            self.assertIsNotNone(match)
            assert match is not None
            self.assertEqual(match["game_name"], "Hades")

    def test_data_manager_exclusions(self):
        user_games = {
            "Witcher3": {
                "user_selected": True,
                "exe_path": "/Games/Witcher3/bin/x64/witcher3.exe",
            }
        }
        excluded = GameDataManager.get_excluded_folders("/Games", user_games)
        self.assertIn("witcher3", excluded)

    def test_game_matcher_orchestration(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sync_dir = Path(tmp_dir)
            game_dir = sync_dir / "Dead Cells"
            game_dir.mkdir()
            (game_dir / "deadcells.exe").write_bytes(b"mock_binary")

            matcher = GameMatcher(sync_folder=str(sync_dir), indexes=self.mock_indexes)
            results = matcher.associate_exes_with_ids()

            self.assertIn("Dead Cells", results)
            self.assertEqual(results["Dead Cells"]["game_name"], "Dead Cells")

    def test_lutris_data_enhancer_enrichment(self):
        from unittest.mock import patch
        from nosteam2steam.identification.lutris import LutrisDataEnhancer

        mock_associate_data = {
            "DeadCells": {
                "game_name": "Dead Cells",
                "exe_path": "/Games/DeadCells/deadcells.exe",
                "steam_id": "588650",
            }
        }

        mock_lutris_results = [
            {
                "name": "Dead Cells",
                "slug": "dead-cells",
                "year": 2018,
                "coverart": "http://img.lutris.net/cover.jpg",
                "provider_games": [{"service": "steam", "slug": "588650"}],
            }
        ]

        with patch("nosteam2steam.identification.lutris.search_lutris_games", return_value=mock_lutris_results):
            enhancer = LutrisDataEnhancer(mock_associate_data)
            enhanced = enhancer.enhance_with_lutris_data()

            self.assertIn("DeadCells", enhanced)
            dc = enhanced["DeadCells"]
            self.assertEqual(dc["name"], "Dead Cells")
            self.assertEqual(dc["source"], "Lutris")
            self.assertEqual(dc["coverart"], "http://img.lutris.net/cover.jpg")
            provider_services = [p["service"] for p in dc["providers"]]
            self.assertIn("steam", provider_services)

    def test_pruning_asset_and_hidden_directories(self):
        from nosteam2steam.identification.scanner import explore_directory_tree

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir) / "MyGame"
            base.mkdir()
            (base / "MyGame.exe").write_bytes(b"bin")

            # Asset directories to prune
            unity_data = base / "MyGame_Data" / "Managed"
            unity_data.mkdir(parents=True)
            (unity_data / "junk.exe").write_bytes(b"junk")

            unreal_content = base / "Content" / "Paks"
            unreal_content.mkdir(parents=True)
            (unreal_content / "assets.pak").write_bytes(b"data")

            hidden_dir = base / ".wine" / "drive_c"
            hidden_dir.mkdir(parents=True)
            (hidden_dir / "notepad.exe").write_bytes(b"junk")

            items = explore_directory_tree(str(base), max_depth=7)
            item_paths = [i["path"] for i in items]

            self.assertIn(str(base / "MyGame.exe"), item_paths)
            self.assertNotIn(str(unity_data / "junk.exe"), item_paths)
            self.assertNotIn(str(unreal_content / "assets.pak"), item_paths)
            self.assertNotIn(str(hidden_dir / "notepad.exe"), item_paths)

    def test_platform_detector_depth_limit_for_generic_configs(self):
        from nosteam2steam.identification.platform import PlatformDetector

        # Shallow config (depth 1) -> detected
        shallow_items = [
            {"path": "/Games/TestGame/config.ini", "depth": 1, "type": "file"}
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".ini", delete=False) as f:
            f.write("AppId = 123456\n")
            shallow_items[0]["path"] = f.name

        info_shallow = PlatformDetector.identify_platform(shallow_items)
        self.assertIsNotNone(info_shallow)
        assert info_shallow is not None
        self.assertEqual(info_shallow["data"]["appid"], "123456")

        # Deep config (depth 4) -> ignored to avoid reading thousands of asset files
        deep_items = [
            {"path": f.name, "depth": 4, "type": "file"}
        ]
        info_deep = PlatformDetector.identify_platform(deep_items)
        self.assertIsNone(info_deep)

    def test_generic_executable_stem_protection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sync_dir = Path(tmp_dir)
            game_dir = sync_dir / "My Custom RPG"
            game_dir.mkdir()
            (game_dir / "Game.exe").write_bytes(b"mock_binary")

            resolver = CandidateResolver(repository=self.repo, sync_folder=str(sync_dir))
            match = resolver.resolve("My Custom RPG", str(game_dir))

            self.assertIsNotNone(match)
            assert match is not None
            # Must keep legitimate folder name instead of false matching random catalog titles
            self.assertEqual(match["game_name"], "My Custom RPG")
            self.assertEqual(match["steam_id"], "")

    def test_download_file_ttl_freshness(self):
        from unittest.mock import patch
        from nosteam2steam.identification.manifests import download_file

        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"existing manifest data")
            tf_path = tf.name

        with patch("requests.head") as mock_head:
            # File is brand new (well within 24h TTL)
            result = download_file("https://example.com/manifest.yaml", tf_path, force=False)
            self.assertFalse(result)
            mock_head.assert_not_called()

    def test_manifest_views_pickle_caching(self):
        import json
        from nosteam2steam.identification.manifests import ManifestRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            index_dir = Path(tmp_dir)
            # Create dummy JSON indexes
            (index_dir / "xml_index.json").write_text(json.dumps({"testgame": "Test Game"}))
            (index_dir / "yaml_index.json").write_text(
                json.dumps({
                    "_metadata": [{"game_name": "Test Game", "steam_id": "111", "gog_id": "222", "lutris_id": "tg", "files": {}}],
                    "by_exe": {"test.exe": 0},
                    "by_path": {},
                    "by_install_dir": {},
                    "by_steam_id": {"111": 0},
                    "by_gog_id": {"222": 0},
                    "by_name": {"test game": 0},
                    "by_name_fuzzy": {},
                })
            )

            # First load should generate manifest_views.pkl
            ManifestRepository(index_dir=str(index_dir))
            pickle_path = index_dir / "manifest_views.pkl"
            self.assertTrue(pickle_path.exists())

            # Delete the JSON index to prove that subsequent loads resolve from the binary pickle cache
            (index_dir / "yaml_index.json").unlink()
            repo2 = ManifestRepository(index_dir=str(index_dir))
            entry = repo2.get_by_steam_id("111")
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertEqual(entry["game_name"], "Test Game")


if __name__ == "__main__":
    unittest.main()
