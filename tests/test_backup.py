"""Unit tests for save backup, hashing, manifest generation, and archive I/O."""

import os
from pathlib import Path
import tempfile
import unittest
import py7zr

import tests.conftest  # noqa: F401
from nosteam2steam.backup.archive import (
    create_file_7z_gbm,
    extract_archive,
    load_metadata_from_7z,
)
from nosteam2steam.backup.creator import (
    assign_os_code,
    generate_config_id,
)
from nosteam2steam.backup.inventory import (
    get_files_date,
    load_sync_record,
    save_sync_record,
)
from nosteam2steam.utils import compute_hash


class TestBackup(unittest.TestCase):
    def test_compute_hash_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Test content for hashing")
            temp_path = f.name

        try:
            h1 = compute_hash(temp_path)
            h2 = compute_hash(temp_path)
            self.assertEqual(h1, h2)
            assert h1 is not None
            self.assertEqual(len(h1), 64)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_compute_hash_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_a = Path(tmp_dir) / "save1.dat"
            file_b = Path(tmp_dir) / "save2.dat"
            file_a.write_bytes(b"data1")
            file_b.write_bytes(b"data2")

            h = compute_hash(tmp_dir)
            self.assertIsInstance(h, str)
            assert h is not None
            self.assertEqual(len(h), 64)

    def test_generate_config_id(self):
        config_save = {"meta_path": "<winAppData>/Saves"}
        cid1 = generate_config_id("TestGame", config_save)
        cid2 = generate_config_id("TestGame", config_save)

        self.assertEqual(cid1, cid2)
        self.assertEqual(len(cid1), 36)

    def test_assign_os_code(self):
        self.assertEqual(assign_os_code([{"os": "windows"}]), 1)
        self.assertEqual(assign_os_code([{"os": "linux"}]), 2)
        self.assertEqual(assign_os_code([{"os": "mac"}]), 3)
        self.assertEqual(assign_os_code([]), 1)

    def test_archive_roundtrip_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_dir = tmp_path / "save_data"
            source_dir.mkdir()
            (source_dir / "savegame.sav").write_bytes(b"Sample save binary data")

            target_archive_dir = tmp_path / "backups"
            archive_path = create_file_7z_gbm(
                source_paths=[source_dir],
                metadata={
                    "config_id": "test-uuid-1234",
                    "game_name": "Hollow Knight",
                    "process_name": "hollow_knight.exe",
                    "original_path": "C:\\Games\\Saves",
                    "meta_path": "<winAppData>\\Saves",
                    "is_folder": True,
                    "os_code": 1,
                    "tags": ["Ludusavi"],
                    "ExcludeList": "",
                    "FileType": "",
                },
                target_dir=target_archive_dir,
                file_name="Hollow Knight [test-uuid-1234].7z",
            )

            self.assertTrue(archive_path.exists())

            metadata = load_metadata_from_7z(archive_path)
            self.assertIsNotNone(metadata)
            assert metadata is not None
            self.assertEqual(metadata["game_name"], "Hollow Knight")
            self.assertEqual(metadata["original_path"], "<winAppData>\\Saves")
            self.assertEqual(metadata["process_name"], "hollow_knight.exe")

            extracted_dir = tmp_path / "restored"
            success = extract_archive(archive_path, extracted_dir, is_folder=True)
            self.assertTrue(success)
            self.assertTrue((extracted_dir / "savegame.sav").exists())
            self.assertEqual((extracted_dir / "savegame.sav").read_bytes(), b"Sample save binary data")

    def test_sync_record_persistence(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            record_path = Path(tmp_dir) / "sync_record.json"
            sample_record = {
                "Hollow Knight": {
                    "/path/to/backup.7z": {
                        "last_sync": "2026-10-29T12:00:00",
                        "updated_from": "local",
                        "hash_backup": "abc123hash",
                        "hash_local": "def456hash",
                    }
                }
            }
            save_sync_record(sample_record, record_path)
            loaded = load_sync_record(record_path)
            self.assertEqual(loaded, sample_record)

    def test_get_files_date(self):
        with tempfile.NamedTemporaryFile() as tmp_file:
            p = Path(tmp_file.name)
            mtime = get_files_date(p)
            self.assertIsNotNone(mtime)

    def test_backup_rotation_to_bak(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_dir = tmp_path / "save_data"
            source_dir.mkdir()
            (source_dir / "save1.sav").write_bytes(b"First version")

            target_archive_dir = tmp_path / "backups"
            meta = {
                "config_id": "test-uuid-rot",
                "game_name": "TestGame",
                "process_name": "test.exe",
                "original_path": "C:\\Saves",
                "meta_path": "<winAppData>\\Saves",
                "is_folder": True,
                "os_code": 1,
            }

            # First backup creation
            first_archive = create_file_7z_gbm(
                source_paths=[source_dir],
                metadata=meta,
                target_dir=target_archive_dir,
                file_name="TestGame [test-uuid-rot].7z",
            )
            self.assertTrue(first_archive.exists())

            # Update save data and create second backup
            (source_dir / "save1.sav").write_bytes(b"Second version")
            second_archive = create_file_7z_gbm(
                source_paths=[source_dir],
                metadata=meta,
                target_dir=target_archive_dir,
                file_name="TestGame [test-uuid-rot].7z",
            )

            bak_file = target_archive_dir / "TestGame [test-uuid-rot].7z.bak"
            self.assertTrue(second_archive.exists())
            self.assertTrue(bak_file.exists())

            # Extract bak file to verify it contains the original version
            restored_bak_dir = tmp_path / "restored_bak"
            extract_archive(bak_file, restored_bak_dir, is_folder=True)
            self.assertEqual((restored_bak_dir / "save1.sav").read_bytes(), b"First version")

    def test_sync_game_no_changes(self):
        from datetime import datetime, timedelta
        from nosteam2steam.backup.restore import sync_game

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_dir = tmp_path / "save_source"
            source_dir.mkdir()
            (source_dir / "save.dat").write_bytes(b"identical save data")

            target_dir = tmp_path / "backups"
            archive_path = create_file_7z_gbm(
                source_paths=[source_dir],
                metadata={
                    "config_id": "id-identical",
                    "game_name": "IdenticalGame",
                    "process_name": "game.exe",
                    "original_path": "C:\\Save",
                    "meta_path": "<winAppData>\\Save",
                    "is_folder": True,
                    "os_code": 1,
                },
                target_dir=target_dir,
                file_name="IdenticalGame.7z",
            )

            local_save_dir = tmp_path / "local_save"
            local_save_dir.mkdir()
            (local_save_dir / "save.dat").write_bytes(b"identical save data")

            # Future sync record matching hashes avoids conflict dialog
            future_sync = datetime.now() + timedelta(days=1)
            record = {
                "IdenticalGame": {
                    str(archive_path): {
                        "last_sync": future_sync.isoformat(),
                        "updated_from": "local",
                        "hash_backup": compute_hash(archive_path),
                        "hash_local": compute_hash(local_save_dir),
                    }
                }
            }
            metadata = {"folder_save": "true"}

            result = sync_game("IdenticalGame", archive_path, local_save_dir, record, metadata)
            self.assertTrue(result)

    def test_verify_archive_integrity(self):
        from nosteam2steam.backup.archive import verify_archive_integrity

        with tempfile.TemporaryDirectory() as tmp_dir:
            good_archive = Path(tmp_dir) / "good.7z"
            with py7zr.SevenZipFile(good_archive, "w") as z:
                z.writestr("sample data", "file.txt")
            self.assertTrue(verify_archive_integrity(good_archive))

            bad_archive = Path(tmp_dir) / "bad.7z"
            bad_archive.write_bytes(b"corrupted 7z archive content")
            self.assertFalse(verify_archive_integrity(bad_archive))

    def test_windows_registry_save_export_and_merge(self):
        from nosteam2steam.backup.registry import (
            export_proton_registry_section,
            merge_proton_registry_section,
            normalize_registry_key,
        )

        hive, subkey = normalize_registry_key("<winRegistry>/HKEY_CURRENT_USER/Software/Developer/MyGame")
        self.assertEqual(hive, "user")
        self.assertEqual(subkey, "Software\\Developer\\MyGame")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pfx = Path(tmp_dir)
            sample_user_reg = """WINE REGISTRY Version 2
;; All keys relative to \\\\User\\\\S-1-5-21-0-0-0-1000

[Software\\\\Developer\\\\MyGame] 1700000000
"SaveSlot"=dword:00000001
"PlayerName"="Hero"

[Software\\\\OtherCompany\\\\OtherApp] 1600000000
"Config"=dword:00000002
"""
            (pfx / "user.reg").write_text(sample_user_reg, encoding="utf-8")

            exported = export_proton_registry_section(pfx, "<winRegistry>/HKEY_CURRENT_USER/Software/Developer/MyGame")
            self.assertIsNotNone(exported)
            assert exported is not None
            self.assertIn('"SaveSlot"=dword:00000001', exported)
            self.assertIn('"PlayerName"="Hero"', exported)
            self.assertNotIn("OtherCompany", exported)

            # Test merging into clean prefix
            target_pfx = Path(tmp_dir) / "new_pfx"
            target_pfx.mkdir()
            (target_pfx / "user.reg").write_text("WINE REGISTRY Version 2\n", encoding="utf-8")

            success = merge_proton_registry_section(target_pfx, exported, hive="user")
            self.assertTrue(success)
            merged_content = (target_pfx / "user.reg").read_text(encoding="utf-8")
            self.assertIn('"PlayerName"="Hero"', merged_content)


if __name__ == "__main__":
    unittest.main()
