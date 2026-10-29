# Changelog

All notable changes to **NoSteam2Steam** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.2.0] - Unreleased

### Added
- **Modular Package Structure:** Refactored codebase into the `nosteam2steam` package, isolating functional domains (`backup`, `identification`, `steam`, `ui`).
- **Heuristic Tree Pruning:** Pruned non-executable asset branches (`*_Data`, `Content/Paks`, `audio`, `textures`, `shaders`, `dlc`), reducing filesystem inode traversal on modern game installations by over 99%.
- **Fast-Path Manifest Probing:** Added constant-time $O(1)$ root checks for `goggame-*.info` and `steam_appid.txt` before scanning subdirectories.
- **Generic Stem Disambiguation:** Introduced `GENERIC_EXECUTABLE_STEMS` validation, requiring cross-correlation with root directory names to prevent false-positive matches on generic binary names (`Game.exe`, `Launcher.exe`, `Main.exe`).
- **Proton Case-Insensitive Path Normalization:** Implemented case-insensitive directory lookups across *ext4* filesystems to discover save games in Proton prefixes irrespective of letter casing.
- **Atomic Archive Writing & Backup Rotation:** Implemented temporary file staging and atomic `os.replace` replacement for `.7z` backup archives, with prior versions rotated to `.bak.7z`.
- **Dynamic Steam Root Resolution:** Replaced static paths with `get_steam_root()` to accurately resolve `<root>/userdata/...` across native and custom Steam configurations.
- **Proton Semantic Numeric Sorting:** Replaced lexicographical sorting with numeric tuple parsing for GE-Proton releases (`GE-Proton10-1` > `GE-Proton9-25`).
- **Headless Test Suite:** Added 77 automated unit tests covering identification, path conversion, backup creation, multi-distribution compatibility, and SteamOS integration, running in under 2 seconds with display server decoupling.
- **Standalone Build Script & CI/CD:** Added `build_standalone.sh` and automated GitHub Actions workflow (`.github/workflows/release.yml`) for automated standalone release builds with SHA-256 checksum generation.
- **Archive Block Integrity Verification:** Implemented `verify_archive_integrity` to validate decompression and CRC blocks via `py7zr.test()` before rotating and committing `.7z` backup archives.
- **KDialog Desktop Fallback:** Implemented native KDialog fallback in `nosteam2steam/ui.py` when `zenity` is not installed on KDE Plasma or minimal desktop environments.
- **Non-Interactive Headless CLI Flags:** Added command-line flags (`--sync`, `--add-games`, `--sync-saves`, `--clean-config`, `-q/--quiet`) for automated scheduling and headless operation without graphical prompts.
- **Windows Registry Saves Support:** Added `nosteam2steam/backup/registry.py` to parse, export, and merge Windows registry save definitions (`<winRegistry>`) from Proton prefix `user.reg` and `system.reg` hives.
- **Dynamic Progress Indicators & Operation Summaries:** Added real-time dynamic progress feedback (`ProgressDialog`) with phase updates during game discovery, SteamGridDB artwork fetching, and save synchronization, alongside structured quantitative completion dialogs.
- **Technical Documentation:** Added `docs/architecture.md` detailing algorithms, mathematical AppID formulas, and architectural invariants.

### Changed
- Standardized application data storage under the XDG Base Directory specification (`~/.local/share/noSteam2Steam`), with automatic migration from legacy `~/noSteam2Steam_Data`.
- Refactored `shortcuts.vdf` manipulation to use pure binary VDF structures with deterministic CRC32 and 64-bit Steam Grid AppID generation.

---

## [1.1.2] - 2025-05-28

### Fixed
- Fixed exception handling when no Proton or GE-Proton compatibility layer is detected in standard Steam paths.

---

## [1.1.1] - 2025-05-28

### Added
- Improved user feedback dialogs during multi-step scanning and synchronization operations.

### Fixed
- Resolved circular import issue in utility modules.

---

## [1.1.0] - 2025-05-27

### Added
- Enhanced manual search workflow for custom executables.
- Optimization of standalone executable build configuration.

---

## [1.0.0] - 2025-05-26

### Added
- Initial standalone executable release for Linux and SteamOS.
- Automated identification of non-Steam games using GOG, Steam, and Lutris databases.
- Shortcut generation into Steam's `shortcuts.vdf`.
- Save game backup and restore compatible with Game Backup Monitor (GBM) `.7z` archive formats.

