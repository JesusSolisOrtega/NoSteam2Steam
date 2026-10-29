"""Unit tests for the universal PE icon extraction subsystem."""

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nosteam2steam.steam.icon_extractor import (
    _build_ico_from_group,
    _build_ico_from_raw_icons,
    _package_ico_entries,
    _parse_image_header,
    _select_best_group_icon,
    extract_icon,
    flexible_extraction_method,
    standart_extraction_method,
)


class TestIconExtractor(unittest.TestCase):
    def test_parse_image_header_png(self):
        # Create a mock PNG IHDR stream (width=256, height=256)
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 256, 256) + b"\x00" * 20
        w, h, planes, bpp = _parse_image_header(png_data)
        self.assertEqual(w, 256)
        self.assertEqual(h, 256)
        self.assertEqual(planes, 1)
        self.assertEqual(bpp, 32)

    def test_parse_image_header_bmp(self):
        # Create a mock BITMAPINFOHEADER (biSize=40, biWidth=48, biHeight=96 for 48x48 icon)
        bmp_data = struct.pack("<IiiHHIIiiII", 40, 48, 96, 1, 32, 0, 0, 0, 0, 0, 0) + b"\x00" * 100
        w, h, planes, bpp = _parse_image_header(bmp_data)
        self.assertEqual(w, 48)
        self.assertEqual(h, 48)
        self.assertEqual(planes, 1)
        self.assertEqual(bpp, 32)

    def test_package_ico_entries(self):
        dummy_bmp = struct.pack("<IiiHH", 40, 32, 64, 1, 32) + b"\x00" * 50
        entries = [
            {"width": 32, "height": 32, "planes": 1, "bit_count": 32, "data": dummy_bmp},
            {"width": 16, "height": 16, "planes": 1, "bit_count": 32, "data": dummy_bmp[:40]},
        ]
        ico_bytes = _package_ico_entries(entries)
        self.assertTrue(ico_bytes.startswith(b"\x00\x00\x01\x00"))
        # Count = 2
        count = struct.unpack("<H", ico_bytes[4:6])[0]
        self.assertEqual(count, 2)

    def test_build_ico_from_group_with_size_alignment_padding(self):
        # GRPICONDIR with 1 icon entry: 32x32, 32bpp, bytes_in_res=50, nID=1
        grp_header = struct.pack("<HHH", 0, 1, 1)
        grp_entry = struct.pack("<BBBxHHIH", 32, 32, 0, 1, 32, 50, 1)
        group_data = grp_header + grp_entry

        # Raw icon image is 54 bytes (4 bytes of alignment padding)
        raw_icon = b"X" * 54
        icon_images = {1: raw_icon}

        ico_bytes = _build_ico_from_group(group_data, icon_images)
        self.assertIsNotNone(ico_bytes)
        assert ico_bytes is not None

        # Verify entry was sliced strictly to 50 bytes, eliminating alignment garbage
        entry_size = struct.unpack("<I", ico_bytes[14:18])[0]
        self.assertEqual(entry_size, 50)

    def test_select_best_group_icon(self):
        # Group 1: 16x16 icon
        grp1 = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBxHHIH", 16, 16, 0, 1, 32, 100, 1)
        # Group 2: 256x256 icon
        grp2 = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBxHHIH", 0, 0, 0, 1, 32, 500, 2)

        icon_images = {1: b"A" * 100, 2: b"B" * 500}
        group_icons = {101: grp1, 102: grp2}

        best = _select_best_group_icon(group_icons, icon_images)
        self.assertEqual(best, grp2)

    def test_build_ico_from_raw_icons_fallback(self):
        # Raw icon without group, valid BMP header
        raw_bmp = struct.pack("<IiiHH", 40, 64, 128, 1, 32) + b"\x00" * 200
        icon_images = {1: raw_bmp}

        ico_bytes = _build_ico_from_raw_icons(icon_images)
        self.assertIsNotNone(ico_bytes)
        assert ico_bytes is not None
        # Entry count = 1
        self.assertEqual(struct.unpack("<H", ico_bytes[4:6])[0], 1)
        # Width byte = 64
        self.assertEqual(ico_bytes[6], 64)

    @patch("nosteam2steam.steam.icon_extractor._extract_best_icon_data")
    def test_extract_icon_end_to_end(self, mock_extract):
        mock_extract.return_value = b"\x00\x00\x01\x00\x01\x00" + b"\x00" * 30

        with tempfile.TemporaryDirectory() as tmp_dir:
            exe_path = Path(tmp_dir) / "game.exe"
            exe_path.touch()
            out_ico = Path(tmp_dir) / "game.ico"

            success = extract_icon(str(exe_path), str(out_ico))
            self.assertTrue(success)
            self.assertTrue(out_ico.exists())

            # Backward-compatibility methods
            s_ok, s_data = standart_extraction_method(str(exe_path))
            self.assertTrue(s_ok)
            self.assertIsNotNone(s_data)

            f_ok, f_data = flexible_extraction_method(str(exe_path))
            self.assertTrue(f_ok)
            self.assertIsNotNone(f_data)

    def test_real_games_icon_extraction_if_present(self):
        """Extracts and validates icons from real game executables present in ~/Games."""
        games_dir = Path.home() / "Games"
        if not games_dir.is_dir():
            self.skipTest("~/Games directory not present on this host")

        # Discover non-installer, non-utility game executables
        real_exes = [
            p
            for p in games_dir.rglob("*.exe")
            if not p.name.lower().startswith(("unins", "install", "unitycrash", "test"))
            and ".wine" not in str(p)
            and "compatibilitytools.d" not in str(p)
            and ".cache" not in str(p)
        ]

        if not real_exes:
            self.skipTest("No real Windows game executables found in ~/Games")

        # Test with up to 6 distinct game executables
        tested = 0
        with tempfile.TemporaryDirectory() as tmp_dir:
            for exe in real_exes[:6]:
                out_path = Path(tmp_dir) / f"{exe.stem}.ico"
                success = extract_icon(str(exe), str(out_path))

                self.assertTrue(success, f"Extraction failed for real game: {exe}")
                self.assertTrue(out_path.is_file(), f"Output file missing for: {exe}")

                data = out_path.read_bytes()
                self.assertGreater(len(data), 1000, f"Icon data suspiciously small for: {exe}")
                self.assertTrue(data.startswith(b"\x00\x00\x01\x00"), f"Invalid ICO header for: {exe}")

                count = struct.unpack("<H", data[4:6])[0]
                self.assertGreaterEqual(count, 1, f"Zero icon resolutions for: {exe}")

                # Validate resolution ordering (highest resolution first)
                resolutions = []
                for i in range(count):
                    entry = data[6 + i * 16 : 6 + (i + 1) * 16]
                    w, h, _, planes, bpp, sz, offset = struct.unpack("<BBBxHHII", entry)
                    w = 256 if w == 0 else w
                    h = 256 if h == 0 else h
                    resolutions.append((w, h, bpp))

                # Verify resolutions are sorted descending
                res_scores = [w * h for w, h, _ in resolutions]
                self.assertEqual(res_scores, sorted(res_scores, reverse=True))
                tested += 1

        self.assertGreaterEqual(tested, 1)


if __name__ == "__main__":
    unittest.main()
