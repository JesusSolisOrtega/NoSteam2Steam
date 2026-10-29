"""Unit tests for atomic persistence and POSIX transactional file safety."""

from pathlib import Path
import tempfile
import unittest

from nosteam2steam.atomic import atomic_write


class TestAtomicWrite(unittest.TestCase):
    def test_atomic_write_text_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "test.txt"
            with atomic_write(target, mode="w", encoding="utf-8") as f:
                f.write("Hello, Atomic World!")

            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "Hello, Atomic World!")

    def test_atomic_write_binary_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "test.bin"
            data = b"\x00\x01\x02\x03\xFF"
            with atomic_write(target, mode="wb") as f:
                f.write(data)

            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes(), data)

    def test_atomic_write_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "deep" / "nested" / "dir" / "file.json"
            with atomic_write(target, mode="w", encoding="utf-8") as f:
                f.write('{"key": "value"}')

            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), '{"key": "value"}')

    def test_atomic_write_rollback_on_exception(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "original.txt"
            target.write_text("Original State", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                with atomic_write(target, mode="w", encoding="utf-8") as f:
                    f.write("Corrupted State Midway")
                    raise RuntimeError("Simulation of process failure")

            # Target must remain completely unmodified
            self.assertEqual(target.read_text(encoding="utf-8"), "Original State")

            # No leftover .tmp files
            tmp_files = list(Path(tmp_dir).glob(".*.tmp_*"))
            self.assertEqual(len(tmp_files), 0)

    def test_atomic_write_backup_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "config.vdf"
            target.write_text("v1_config", encoding="utf-8")

            with atomic_write(target, mode="w", encoding="utf-8", backup=True) as f:
                f.write("v2_config")

            self.assertEqual(target.read_text(encoding="utf-8"), "v2_config")
            bak_file = target.with_name("config.vdf.bak")
            self.assertTrue(bak_file.exists())
            self.assertEqual(bak_file.read_text(encoding="utf-8"), "v1_config")


if __name__ == "__main__":
    unittest.main()
