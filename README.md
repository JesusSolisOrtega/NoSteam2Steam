# NoSteam2Steam

<p align="center">
  <a href="https://github.com/JesusSolisOrtega/NoSteam2Steam/releases/latest">
    <img src="https://img.shields.io/github/v/release/JesusSolisOrtega/NoSteam2Steam?color=blue&style=flat-square" alt="Latest Release">
  </a>
  <img src="https://img.shields.io/badge/Platform-SteamOS%20%7C%20Linux-informational?style=flat-square" alt="Platform">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square" alt="Python Version">
  <img src="https://img.shields.io/badge/License-Personal%20%26%20Educational-green?style=flat-square" alt="License">
  <a href="https://ko-fi.com/F1F51F88U3">
    <img src="https://img.shields.io/badge/Donate-Ko--fi-FF5E5B?style=flat-square&logo=ko-fi&logoColor=white" alt="Donate on Ko-fi">
  </a>
  <a href="https://www.paypal.com/donate/?hosted_button_id=VVRC7ZTVFJWDU">
    <img src="https://img.shields.io/badge/Donate-PayPal-00457C?style=flat-square&logo=paypal&logoColor=white" alt="Donate on PayPal">
  </a>
</p>

**NoSteam2Steam** is an automated utility for Linux distributions (SteamOS, Arch, Fedora, Debian, Ubuntu, openSUSE) that discovers non-Steam games across native, Flatpak, and Snap package environments, registers them into Steam with official artwork and optimal compatibility settings, and synchronizes save game backups adhering to the **Game Backup Monitor (GBM)** standard.

---

## Key Features

- **Multi-Distribution & Multi-Package Support:** Native package systems (Pacman, DNF, APT, Zypper), Flatpak Steam (`com.valvesoftware.Steam`), Snap, and custom installations via `$STEAM_DIR`.
- **Automated Game Discovery:** Scans game directories (e.g., `~/Games`, Heroic, Lutris, Bottles, and external mounts under `/run/media`, `/media`, and `/mnt`), matching metadata from GOG, Steam, and Lutris catalogs.
- **Steam Integration:**
  - Automatically updates `shortcuts.vdf` with generated entries and alphabetical reindexing.
  - Generates 32-bit shortcut IDs and 64-bit AppIDs for Steam Grid artwork.
  - Automatically extracts application icons from Windows `.exe` headers and fetches cover art, banners, and logos.
  - Detects and assigns the highest available Proton or GE-Proton compatibility layer across system-wide and user directories.
- **Save Game Backup and Synchronization:**
  - Full compatibility with the Game Backup Monitor (GBM) `.7z` archive format.
  - Bidirectional synchronization between local save directories and a centralized backup folder.
  - Discovers save prefixes across all storage drives and secondary Steam libraries registered in `libraryfolders.vdf`.
  - Translates Windows environment paths (`<winAppData>`, `<winDocuments>`, etc.) and Linux native paths (`<xdgDataHome>`, `<xdgConfigHome>`) using case-insensitive path resolution on *ext4*.
  - Windows registry save support (`<winRegistry>`) via extraction and merge of Proton prefix `user.reg` and `system.reg` hives.
  - Archive block decompression and CRC integrity verification prior to rotating and committing `.7z` backups.
  - Atomic archive writes and backup rotation (`.7z.bak`) to prevent file corruption.
- **Dual Dialog Backend & Headless Operation:** Native `zenity` with automatic fallback to `kdialog` on KDE Plasma desktops, and full CLI flag support for cron/systemd automation.
- **Self-Contained Standalone Executable:** Distributed as a single binary with zero external package dependencies.

---

## Installation & Quick Start

### Option 1: Standalone Binary (Recommended)

No installation or configuration of Python packages is required. The standalone executable bundles all runtime dependencies (`py7zr`, `vdf`, `pefile`, etc.):

1. Download the latest `noSteam2Steam.bin` from the [Releases](https://github.com/JesusSolisOrtega/NoSteam2Steam/releases/latest) page.
2. Place the file in your preferred directory (for example, on your `~/Desktop`).
3. Grant execution permissions:
   ```bash
   chmod +x noSteam2Steam.bin
   ```
4. Run the application by double-clicking the file in Desktop Mode or launching it from the terminal:
   ```bash
   ./noSteam2Steam.bin
   ```

*(Note: A graphical dialog provider (`zenity` or `kdialog`) is required for interactive menus. `zenity` is pre-installed on SteamOS by default; `kdialog` is used automatically on KDE Plasma systems where `zenity` is absent.)*

---

### Option 2: Automated Desktop Installer

If you prefer an automated setup that copies files to `~/Games/noSteam2Steam` and creates a `.desktop` shortcut on your Desktop:

```bash
git clone https://github.com/JesusSolisOrtega/NoSteam2Steam.git
cd NoSteam2Steam
chmod +x installer.sh
./installer.sh
```

---

### Option 3: From Source (For Developers)

```bash
git clone https://github.com/JesusSolisOrtega/NoSteam2Steam.git
cd NoSteam2Steam
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python3 -m nosteam2steam
```

To compile a standalone binary locally, run:
```bash
./build_standalone.sh
```

---

## Usage

When executed, NoSteam2Steam displays the main graphical menu with the following operations:

| Option | Action | Description |
| :--- | :--- | :--- |
| **1** | **Automatic Sync** | Full automated pipeline: discovers games, adds them to Steam with artwork, and synchronizes save backups. |
| **2** | **Add Games to Steam Automatically** | Runs the identification and Steam shortcut registration passes without performing save synchronization. |
| **3** | **Game Saves Synchronization** | Synchronizes local Proton save files with the backup folder (restores missing saves or updates backups). |
| **4** | **Manually Add a Game to Steam** | Prompts you to browse for an executable, search metadata, and register a custom game entry. |
| **5** | **Clean NoSteam2Steam Configuration** | Selective maintenance utility to clear configuration mappings, cached inventories, or downloaded artwork. |
| **6** | **Enable / Disable Syncthing** | Toggles the background synchronization service for multi-device save replication. |
| **7** | **Change Synchronized Game Folders** | Adds or removes monitored directories where games and saves are discovered (defaults: `~/Games`, `~/Games/Heroic`). |
| **8** | **Exit** | Closes the application. |

### Command-Line Interface (CLI / Headless Mode)

For automated tasks, headless execution, or scheduling via `cron` or `systemd`, NoSteam2Steam supports direct CLI parameters:

```bash
# Run full automated scan, shortcut registration, and save sync without GUI prompts
./noSteam2Steam.bin --sync --quiet

# Add games and artwork to Steam without syncing saves
./noSteam2Steam.bin --add-games

# Sync save backups without scanning for new games
./noSteam2Steam.bin --sync-saves

# Reset configuration caches non-interactively
./noSteam2Steam.bin --clean-config
```

| Flag | Description |
| :--- | :--- |
| `--sync`, `--auto` | Executes full pipeline: discovers games, updates shortcuts, and synchronizes saves. |
| `--add-games` | Scans directories and registers shortcuts and artwork without touching save backups. |
| `--sync-saves` | Synchronizes save files with the backup folder without directory scanning. |
| `--clean-config` | Clears local game configurations non-interactively. |
| `-q`, `--quiet` | Suppresses graphical dialog notifications, logging progress directly to standard output. |

> [!IMPORTANT]
> Steam must be completely closed before modifying `shortcuts.vdf`. NoSteam2Steam detects if Steam is currently running and provides a prompt to close it gracefully to avoid file-locking conflicts.

---

## Save Synchronization and Multi-Device Setup

NoSteam2Steam uses **Game Backup Monitor (GBM)** archive specifications for save game backups:

- **Default Backup Directory:** `~/Backups` (configurable via `alternative_backups_path.txt` or via menu).
- **Format:** Standard `.7z` archives containing save files and a JSON metadata header describing original paths and timestamps.
- **Cross-Platform Sync:** Save archives can be synced seamlessly between your Steam Deck and a Windows PC using tools such as **Syncthing** (Syncthingy on Steam Deck), cloud storage, or local network transfers.

---

## Support and Donations

NoSteam2Steam is an independent, free, and open-source project created and maintained for the Linux and Steam Deck gaming community.

If this tool has saved you time or improved your experience on the Steam Deck, please consider supporting continued development, hardware testing, and maintenance:

<div align="center">

[![Donate on Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20the%20Project-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/F1F51F88U3)
&nbsp;&nbsp;&nbsp;&nbsp;
[![Donate on PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://www.paypal.com/donate/?hosted_button_id=VVRC7ZTVFJWDU)

<br>

<a href="https://ko-fi.com/F1F51F88U3" target="_blank">
  <img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Buy Me A Coffee" height="38">
</a>

<p><i>Every contribution, no matter the size, is sincerely appreciated. Thank you!</i></p>

</div>

---

## Technical Documentation & Contributing

- For in-depth technical documentation covering filesystem pruning algorithms, Steam AppID mathematical calculations, and Proton prefix conversion mechanics, see the [Technical Architecture Specification](docs/architecture.md).
- For coding conventions, static analysis guidelines, and test execution standards, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Credits and References

- **Game Backup Monitor (GBM):** Specification for save backups and metadata structure ([mikemaximus.github.io/gbm-web](https://mikemaximus.github.io/gbm-web/)).
- **Ludusavi Manifest:** Multi-platform save file directory specifications ([github.com/mtkennerly/ludusavi-manifest](https://github.com/mtkennerly/ludusavi-manifest)).
- **Lutris:** Metadata provider and runner data ([lutris.net](https://lutris.net/)).
- **Valve Python VDF:** KeyValues parsing and serialization implementation.
- **Steam Shortcut Manager & SteamRomManager:** Reference implementations for AppID derivation and binary shortcut structures.

---

## License

Copyright (c) 2025 Jesús Solís Ortega.

This software is distributed for **educational and personal use only**. Commercial use, distribution, sublicensing, sale, or integration into for-profit products or services is prohibited without prior written consent from the author. Non-commercial use, copying, and modification are permitted provided that this copyright notice remains intact.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.
