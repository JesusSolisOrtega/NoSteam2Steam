# Technical Architecture Specification

This document provides a detailed technical reference for the architecture, data structures, algorithms, and subsystem interactions of **NoSteam2Steam**.

---

## 1. System Overview

NoSteam2Steam automates three interconnected domains within Linux and SteamOS gaming environments:
1. Discovery and heuristic identification of non-Steam game installations.
2. Registration, asset fetching, and compatibility layer assignment in the Steam client.
3. Save file synchronization and archiving adhering to the Game Backup Monitor (GBM) specification.

```mermaid
flowchart TD
    subgraph Discovery ["1. Identification Pipeline"]
        A["Root Directories (~/Games)"] --> B["Scanner & Directory Cache"]
        B -->|Prune asset dirs| C["Heuristic Filter"]
        C --> D{"Fast Probe O(1)"}
        D -->|Found| E["Platform Resolver (GOG/Steam)"]
        D -->|Not Found| F["Manifest Resolver (XML/YAML/Lutris)"]
        E --> G["Candidate Disambiguation"]
        F --> G
    end

    subgraph Integration ["2. Steam Integration"]
        G --> H["AppID & Shortcut ID Math"]
        H --> I["Proton Semantic Version Ranker"]
        I --> J["Binary VDF Serialization"]
        J --> K["Steam shortcuts.vdf"]
        H --> L["Artwork & Icon Extraction"]
        L --> M["Steam Grid Cache"]
    end

    subgraph Backup ["3. Save Synchronization"]
        N["GBM / Ludusavi Save Paths"] --> O["PathConverter (Proton ext4 Normalization)"]
        O --> P["SHA-256 State Evaluator"]
        P --> Q{"Conflict Analysis"}
        Q -->|In Sync| R["No-op"]
        Q -->|Backup Newer| S["Restore Archive"]
        Q -->|Local Newer| T["Atomic .7z Writer & .bak Rotation"]
    end
```

---

## 2. Identification Subsystem

### 2.1 The Filesystem Traversal Problem

On Linux file systems (notably *ext4* on SteamOS internal NVMe drives and *ext4/exFAT/btrfs* on MicroSD cards), naive recursive directory traversal poses severe performance limitations. Modern game engines (e.g., Unity, Unreal Engine) distribute thousands of static asset files across deep hierarchies. For example, a standard game installation may contain over 13,000 files, with more than 99.8% located within `*_Data` or `Content/Paks` subdirectories.

Traversing these asset directories causes excessive random inode lookups, which on MicroSD storage with cold VFS caches can introduce 2 to 5 seconds of latency per game directory. Furthermore, Proton prefixes contain `.wine/dosdevices/z:` symlinks pointing to `/`, which can cause uncontrolled traversals into system root filesystems if symlinks and hidden directories are not strictly isolated.

### 2.2 Heuristic Tree Pruning

To maintain bounded $O(K)$ traversal cost (where $K$ represents the count of candidate binary nodes rather than total game assets), the scanner implements strict heuristic pruning in `nosteam2steam.identification.scanner`:

1. **Asset Directory Pruning:** Any directory whose lower-case name matches known asset containers is discarded immediately without inspecting its children:
   $$\text{Prune}(D) \iff D \in \{\text{content}, \text{paks}, \text{audio}, \text{sound}, \text{music}, \text{textures}, \text{shaders}, \text{dlc}, \dots\} \lor D \text{ ends with } \texttt{\_data}$$
2. **Hidden Directory and Symlink Isolation:** Hidden directories (names beginning with `.`) and symbolic links are excluded at the directory collection phase, preventing infinite loops or traversal of host filesystem trees via Wine prefix symlinks.
3. **Directory Tree Memoization:** The `DirectoryCache` stores evaluated trees per root folder, ensuring that subsequent matching passes (`PlatformResolver`, `CandidateResolver`) reuse existing in-memory directory structures rather than issuing redundant `os.walk` or `os.scandir` system calls.

### 2.3 Fast-Path Root Probing

Before executing deep manifest or catalog searches, the platform resolver performs constant-time $O(1)$ probes in the game root folder:
- **GOG Game Manifest:** Direct check for `goggame-*.info`. If present, title, game ID, and launcher executable are read directly from JSON.
- **Steam AppID File:** Direct check for `steam_appid.txt`. If present, the numerical AppID is mapped to existing Steam catalog data.
- **Auxiliary Manifests:** Files such as `.ini`, `.cfg`, and `.json` are evaluated up to a bounded maximum depth ($D \le 2$).

### 2.4 Stem Disambiguation for Generic Binary Names

Certain executable files share common generic binary names across distinct titles (e.g., `Game.exe`, `Launcher.exe`, `Main.exe`, `start.exe`). Matching such binaries strictly by filename against global databases (such as PCGamingWiki or Lutris catalogs) results in false positive collisions.

The candidate resolver enforces a disambiguation guard:
```python
if stem.lower() in GENERIC_EXECUTABLE_STEMS:
    score = simple_match_score(folder_name, candidate_name)
    if score < 50:
        # Reject candidate to avoid false-positive catalog misidentification
        continue
```
This guarantees that an executable named `Game.exe` inside a directory `/Games/Hades/` is not falsely classified as an unrelated historical title whose primary binary was also cataloged as `Game.exe`.

### 2.5 Binary Selection and Architecture Ranking

When multiple candidate executables exist within a game directory, the ranking algorithm selects the optimal target based on binary architecture and graphics API markers:
$$\text{Rank}(E) = w_{\text{arch}} + w_{\text{api}} - w_{\text{demote}}$$
- **Architecture Weight ($w_{\text{arch}}$):** Prioritizes 64-bit targets (`x64`, `64`, `win64`, `x86_64`) over 32-bit targets (`x86`, `win32`, `32`).
- **Graphics API Weight ($w_{\text{api}}$):** Prioritizes explicit Vulkan targets (`vk`, `vulkan`) over standard DirectX targets.
- **Demotion Penalty ($w_{\text{demote}}$):** Penalizes secondary tools (`crashreport`, `unins000`, `helper`, `setup`, `config`).

### 2.6 Unmatched Candidate Cataloging and Guided Manual Registration

When a game directory is traversed but fails to achieve an automated catalog match, `nosteam2steam.identification.matcher.GameMatcher` inspects the directory structure up to a bounded depth ($D \le 3$) to identify prospective executable binaries, filtering out setup, uninstaller, and engine crash handlers.

Discovered candidates are serialized atomically into `unmatched_candidates.json`:
```json
[
  {
    "folder_name": "HollowKnight",
    "folder_path": "/home/user/Games/HollowKnight",
    "exe_path": "/home/user/Games/HollowKnight/hollow_knight.exe",
    "all_exes": ["/home/user/Games/HollowKnight/hollow_knight.exe"]
  }
]
```

The manual addition assistant (`nosteam2steam.identification.manual_adder.manual_add_game`) ingests this catalog at launch:
1. **Interactive Candidate Selection:** Presents detected unassigned titles directly to the user in a graphical menu prior to prompting for file-browser navigation.
2. **Atomic Catalog Eviction:** Upon successful registration and persistence of the game into `games.json`, the corresponding executable entry is purged from `unmatched_candidates.json` using atomic replacement to prevent stale queue accumulation.

---

## 3. Steam Integration Subsystem

### 3.1 Mathematical AppID and Shortcut ID Computation

Steam calculates shortcut identifiers using a combination of 32-bit CRC32 checksums and bitwise operations:

1. **Base CRC32 Calculation:**
   Given the shortcut target executable path $T$ and the game display name $N$:
   $$K = T \mathbin{\Vert} N$$
   $$C = \text{CRC32}(K) \mid \mathtt{0x80000000}$$
   $$\text{shortcut\_id} = C \pmod{2^{32}}$$

2. **64-bit Steam Grid AppID:**
   Steam associates custom artwork (grid banners, posters, hero images) using a 64-bit unsigned identifier derived from the top 32 bits of the CRC32 checksum:
   $$\text{top\_32} = C \gg 32$$
   $$\text{grid\_app\_id} = (\text{top\_32} \ll 32) \mid \mathtt{0x02000000}$$

This calculation guarantees exact parity with Valve's desktop client conventions and SteamGridDB asset mapping.

### 3.2 Compatibility Tool Selection

SteamOS allows assigning specific Proton versions to individual non-Steam shortcuts via `config.vdf`. NoSteam2Steam determines the highest available compatibility tool using semantic numeric ordering:

1. **GE-Proton:** Parsed as tuples of integers:
   $$\text{Version}(\texttt{GE-Proton10-1}) = (10, 1) > \text{Version}(\texttt{GE-Proton9-25}) = (9, 25)$$
   This prevents lexicographical sort failures where `GE-Proton9-*` would erroneously supersede `GE-Proton10-*`.
2. **Official Proton:** Evaluated with priority on `Proton Experimental`, followed by the highest numbered release (e.g., `Proton 9.0` over `Proton 8.0`).

### 3.3 Portable Executable (PE) Icon Extraction

To provision application icons without requiring internet connectivity:
1. The Windows `.exe` binary is parsed using `pefile` to locate the resource directory (`RT_GROUP_ICON` and `RT_ICON`).
2. The largest available icon resource (e.g., 256x256 PNG-compressed or uncompressed DIB) is extracted.
3. An ICO container header is synthesized and written to Steam's icon cache directory:
   $$\sim\texttt{/.local/share/Steam/userdata/}\{U\}\texttt{/config/icons/}\{\text{app\_id}\}\texttt{.ico}$$

---

## 4. Save Game & Backup Subsystem

### 4.1 GBM Archive Specification

NoSteam2Steam conforms to the Game Backup Monitor (GBM) standard:
- **Archive Format:** `.7z` container compressed with LZMA/LZMA2.
- **Embedded Metadata:** Each archive stores a JSON metadata structure detailing original Windows paths, configuration identifiers, file modification timestamps, and game signatures.

### 4.2 Proton Prefix Normalization and Path Conversion

Windows games running under Proton store save data inside prefix virtual C: drives located at:
$$\sim\texttt{/.local/share/Steam/steamapps/compatdata/}\{\text{app\_id}\}\texttt{/pfx/drive\_c/}$$
On multi-drive or containerized configurations, prefixes may reside under secondary library paths registered in `libraryfolders.vdf`, Flatpak Steam (`~/.var/app/com.valvesoftware.Steam/...`), or Snap Steam (`~/snap/steam/common/...`). The resolver dynamically queries `get_all_compatdata_dirs()` to locate prefixes across all mounted storage volumes.

Path conversions map environment variables to filesystem targets:

| Variable | Target Path / Subdirectory |
| :--- | :--- |
| `<winAppData>` | `users/steamuser/AppData/Roaming` |
| `<winLocalAppData>` | `users/steamuser/AppData/Local` |
| `<winDocuments>` | `users/steamuser/Documents` |
| `<winSavedGames>` | `users/steamuser/Saved Games` |
| `<root>` | Base Steam directory (parent of `userdata` and `steamapps`) |
| `<xdgDataHome>` | `$XDG_DATA_HOME` or `~/.local/share` (Linux native saves) |
| `<xdgConfigHome>` | `$XDG_CONFIG_HOME` or `~/.config` (Linux native configs) |
| `<xdgStateHome>` | `$XDG_STATE_HOME` or `~/.local/state` |

#### Case-Insensitive Traversal on ext4
Windows file systems (NTFS) are case-preserving and case-insensitive, whereas Linux native file systems (*ext4*) are case-sensitive. A game expecting `Documents/My Games/Save.dat` will fail to locate existing saves if a directory was generated as `documents/my games/save.dat`.

The `PathConverter.search_paths` method executes case-insensitive path traversal using directory entry normalization, locating the correct path regardless of letter casing discrepancies across the virtual prefix.

### 4.3 Pre-flight Storage Verification, Atomic Writing, and Snapshot Rollback

To prevent archive corruption, filesystem exhaustion, or catastrophic data loss during compression:

```
[Pre-flight Verification]
Calculate Source Bytes ───> Free Space Check (Required + 50 MB Margin) ───> Proceed / Raise OSError

[Staging Phase]
Source Save Data ───> Compress & Embed XML ───> Test Archive Blocks (testzip) ───> .[Archive].tmp.7z

[Rotation Phase]
Existing [Archive].7z ───> Atomic Rotate (os.replace) ───> [Archive].7z.bak

[Commit Phase]
.[Archive].tmp.7z ───> Atomic Replace (os.replace) ───> [Archive].7z

[Rollback Phase (On Demand)]
[Archive].7z.bak ───> Atomic Restore (rollback_backup) ───> [Archive].7z
```

1. **Pre-flight Quota Guards:** Before executing 7-Zip compression routines in `nosteam2steam.backup.archive`, source directories and files are evaluated using `calculate_source_size`. The storage capacity of the destination mount point is verified via `shutil.disk_usage`. If free capacity fails to satisfy `required_bytes + 50 MB`, an `OSError` is raised immediately, avoiding partial archive creation.
2. **Staging & Integrity Verification:** The `.7z` container is generated in a staging file `.[name].tmp.7z`. Prior to committing, `verify_archive_integrity` extracts archive blocks in memory (`py7zr.testzip()`). Corrupted archives fail fast without touching production data.
3. **Snapshot Rotation:** The prior archive is rotated to `[name].7z.bak` via POSIX `os.replace`.
4. **Atomic Commit:** The staged temporary archive replaces the target path atomically on the filesystem.
5. **Snapshot Recovery Protocol (Rollback):** Should a sync operation overwrite valid save data or if archive regression occurs, `nosteam2steam.backup.restore.rollback_backup` restores `[name].7z` from `[name].7z.bak`. This recovery operation is exposed interactively in the Save Manager via `handle_rollback_dialog`.

### 4.4 Audit Trail, Conflict Resolution, and Synchronization History

Save synchronization state is tracked persistently in `sync_record.json`. To enable auditability and informed user conflict resolution:

```json
{
  "GameName": {
    "last_sync": "2026-10-30T00:15:00.000000",
    "updated_from": "local",
    "hash_backup": "a8f3...b291",
    "hash_local": "a8f3...b291",
    "has_rollback": true,
    "history": [
      {
        "timestamp": "2026-10-30T00:15:00.000000",
        "action": "local",
        "hash_backup": "a8f3...b291",
        "hash_local": "a8f3...b291"
      }
    ]
  }
}
```

1. **Sliding Audit Window:** Each game record maintains a rolling 10-event transaction history recording timestamps, transfer directions (`"local"` for local save $\rightarrow$ backup, or `"backup"` for backup $\rightarrow$ local), and computed SHA-256 hashes.
2. **Direction-Aware Conflict Disambiguation:** When local and remote save states diverge, `nosteam2steam.backup.conflict.show_sync_conflict_dialog` presents timestamps, hash divergence, and explicitly indicates the direction of the previous transfer (*Local save $\rightarrow$ Backup repository* or *Backup repository $\rightarrow$ Local save*).
3. **Dual Dialog Backend Integration:** Conflict prompts dynamically route through Zenity or KDialog (`--warningyesnocancel`), preserving three-state resolution (*Use Backup*, *Use Local*, or *Cancel*) across GNOME, KDE Plasma, and SteamOS Game Mode.

### 4.5 Inventory Metadata, Registry Preservation, and Incremental Caching

The cataloging engine (`nosteam2steam.backup.inventory`) indexes existing save archives in `games_backups_inventory.json`:

```json
{
  "Hollow Knight": [
    {
      "folder": "Hollow Knight [uuid-1234]",
      "executable": "hollow_knight.exe",
      "most_recent_7z_file": "Hollow Knight [uuid-1234].7z",
      "7z_files": {
        "Hollow Knight [uuid-1234].7z": {
          "original_path": "<winRegistry>/HKEY_CURRENT_USER/Software/Team Cherry",
          "folder_save": "true",
          "modification_date": "2026-10-30T00:10:00.000000",
          "size_bytes": 1048576,
          "has_registry": true
        }
      }
    }
  ]
}
```

1. **Size and Registry Metrics:** Each archive entry records `size_bytes` and a boolean `has_registry` flag, displayed in backup selection dialogs (`[REGISTRY]` marker and formatted metric strings).
2. **Windows Registry Preservation:** When save paths target `<winRegistry>`, `nosteam2steam.backup.registry` parses Proton `user.reg` and `system.reg` hives, serializes relevant subkeys into an isolated `_registry_backup.reg` text stream, and embeds it inside the `.7z` container. On restoration, keys are merged cleanly into the destination prefix.
3. **Incremental Cache Optimization:** Scanning dozens of multi-megabyte archives would introduce significant CPU overhead if XML manifests were decompressed on every run. `generate_games_inventory` inspects archive filesystem modification times (`st_mtime`). If the timestamp matches the cached `modification_date`, metadata is ingested from disk cache in $O(1)$ time, skipping 7-Zip decompressor instantiation.

---

## 5. System Resiliency and Localization Subsystems

### 5.1 Atomic File Writing Context Manager (`nosteam2steam.atomic`)

To protect configuration and state files (`shortcuts.vdf`, `games.json`, `sync_folders.txt`, `games_backups_inventory.json`, `sync_record.json`, `unmatched_candidates.json`) against truncation during unexpected process termination or system reboot, the codebase utilizes an independent atomic writer:

```python
with atomic_write(filepath, mode="w", encoding="utf-8") as f:
    json.dump(data, f, indent=4)
```

- **Colocated Staging:** Writes to a sibling staging file (`.{filename}.[pid].tmp`) within the identical parent directory, ensuring that staging and destination reside on the same filesystem mount point.
- **Physical Sync:** Executes `f.flush()` followed by `os.fsync(f.fileno())` before closure to force disk cache commit.
- **Pre-Commit Snapshot:** Generates a `.bak` copy of the destination prior to replacement.
- **POSIX Replace:** Commits the staging file via `os.replace`, guaranteeing an atomic directory entry switch.

### 5.2 Localization and Internationalization Engine (`nosteam2steam.i18n`)

The i18n subsystem provides comprehensive internationalization across 20 language variants:

1. **System Locale Detection:** Evaluates environment variables in order (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`), with heuristic resolution for dialects such as Valencian (`@valencia` or `val_*` $\rightarrow$ `ca`) and Pakistani Urdu (`ur_*` $\rightarrow$ `ur`).
2. **Lazy-Loaded JSON Catalogs:** Translation dictionaries in `nosteam2steam/locales/<lang>.json` are loaded on demand and cached in memory.
3. **String Interpolation & Fallback:** The translation macro `_("String {param}", param=value)` resolves against the active catalog. If a key is missing or formatting fails, it degrades gracefully to the English default template without raising exceptions.
4. **Token Consistency Enforcement:** AST and regular expression validators verify that format tokens (`{name}`, `{game}`, `{date}`, `{status}`) match identically between source English strings and all 20 translation catalogs.

### 5.3 XDG Desktop Integration (`nosteam2steam.desktop`)

Automates installation, state inspection, and maintenance of standard Freedesktop XDG desktop entries:
- Generates compliant `.desktop` configuration referencing the standalone binary (`sys.frozen`), `launch.sh`, or the active Python interpreter.
- Preserves the application icon in a persistent user directory (`~/.local/share/noSteam2Steam/assets/icon.png`) to avoid resource invalidation upon PyInstaller runtime teardown.
- Dynamically resolves localized desktop directories via `xdg-user-dir DESKTOP` with home directory boundary validation and internationalized directory fallbacks (`Escritorio`, `Schreibtisch`, `Bureau`, `Desktop`).
- Deploys executable desktop files to `~/.local/share/applications/nosteam2steam.desktop` (Application Menu) and the localized desktop path, configuring `metadata::trusted true` attributes for seamless execution on KDE Plasma and SteamOS.
- Provides status detection (`is_desktop_entry_installed`), interactive toggle management via graphical UI dialogs, and programmatic control through CLI switches (`--install-desktop`, `--uninstall-desktop`).

---

## 6. Verification and Quality Assurance Standards

### 6.1 Test Execution Architecture

All automated tests in `tests/` operate under isolated headless conditions:
- **Display Server Decoupling:** `DISPLAY` and `WAYLAND_DISPLAY` environment variables are unset during test initialization (`tests/__init__.py`), preventing processes from attempting graphical display connections.
- **Subprocess Interception:** Invocations of `zenity` via `subprocess.run` or `subprocess.Popen` are intercepted by test hooks in `tests/conftest.py` and `tests/__init__.py`, returning synthetic responses in memory (`MagicMock`) without launching external operating system processes.
- **Temporary Filesystem Sandboxing:** All file generation and archive manipulation tests execute within transient `tempfile.TemporaryDirectory` instances, ensuring that no host system or Steam client configuration files are altered during testing.

### 6.2 Static Analysis and Typing Verification

Code quality and interface soundness are validated through static analysis tooling:
- **Static Type Checking:** Enforces explicit type annotations conforming to PEP 484 and PEP 526 across all module interfaces. Code must achieve 0 errors and 0 warnings under both `mypy` and `pyright`:
  ```bash
  mypy nosteam2steam tests
  pyright nosteam2steam tests
  ```
- **Linting and Style Rules:** Formatting rules are enforced via `ruff` with a target line length of 120 characters:
  ```bash
  ruff check nosteam2steam tests
  ```

---

## 7. Codebase Architecture & Implementation Guidelines

### 7.1 Package Organization and Module Responsibilities

The codebase follows a modular design isolating functional domains into dedicated subpackages:

```
nosteam2steam/
├── backup/              # Game Backup Monitor archive generation, restoration, path translation
│   ├── archive.py       # .7z compression, metadata packing, integrity testing, atomic replacement
│   ├── conflict.py      # Timestamp, hash evaluation, and direction-aware conflict resolution
│   ├── inventory.py     # Backup cataloging, size metric calculation, and mtime incremental caching
│   ├── manager.py       # High-level backup synchronization and rollback workflow controller
│   ├── path_converter.py# Windows path variable translation to Proton prefix filesystem paths
│   ├── registry.py      # Proton prefix Windows registry (<winRegistry>) export and merge
│   └── restore.py       # Archive extraction, save restoration, rollback, and sync engine
├── identification/      # Discovery and heuristic classification of game binaries
│   ├── candidates.py    # Manifest parsing, XML/YAML definitions, and candidate scoring
│   ├── heuristics.py    # Executable naming rules, suffix stripping, and architecture ranking
│   ├── manual_adder.py  # Unmatched candidate picker and manual Lutris/Steam registration
│   ├── matcher.py       # Directory tree coordination and candidate matching pipeline
│   ├── platform.py      # Root-level fast probe for GOG and Steam configuration files
│   └── scanner.py       # Inode traversal with asset directory pruning and directory caching
├── steam/               # Steam client ecosystem integration
│   ├── compat.py        # Proton and Proton-GE semantic version sorting and selection
│   ├── grid.py          # SteamGridDB asset downloading and caching
│   ├── icon_extractor.py# Windows PE icon extraction and ICO file generation
│   ├── ids.py           # CRC32 and FNV AppID / shortcut ID mathematical generation
│   └── shortcuts.py     # Binary VDF parsing, serialization, and alphabetical reindexing
├── locales/             # Compiled JSON translation catalogs for 20 language variants
├── atomic.py            # Zero-dependency atomic file writing and .bak creation context manager
├── desktop.py           # XDG desktop entry specification generator and system installer
├── i18n.py              # Internationalization engine, environment locale detection, and fallback
├── config.py            # Global configuration constants, environment detection, and path discovery
├── dialogs.py           # Wizard dialogs and user maintenance options
├── ui.py                # Abstraction layer for Zenity and KDialog dialogs
└── app.py               # Main menu controller and headless CLI entry point
```

### 7.2 Architectural Invariants and Recommendations

When extending or modifying the codebase, the following architectural invariants should be preserved:

1. **Decoupling of Presentation and Domain Logic:**
   Core business logic modules (`identification`, `steam`, `backup`) must never directly execute UI commands via `subprocess.run(["zenity", ...])`. All user interaction should route through `nosteam2steam.ui` or designated wizard controllers. This maintains testability in headless environments and allows alternative user interfaces (e.g., Qt, Web, or pure CLI) to be introduced without modifying domain logic.

2. **Filesystem Portability and Dynamic Root Detection:**
   Never assume fixed developer usernames or paths (such as `/home/<user>`). Paths must be dynamically resolved using:
   - `Path.home()` for user directory root.
   - `nosteam2steam.config.ROOT_PATH` for base Steam installations (accommodating native Steam, Flatpak paths, and custom library folders).
   - `nosteam2steam.config.get_noSteam2Steam_dir()` for application data adhering to the XDG Base Directory specification (`~/.local/share/noSteam2Steam`).

3. **Deterministic Error Handling and Structured Logging:**
   - Avoid catching broad `Exception` clauses silently. Catch specific recoverable exceptions (`FileNotFoundError`, `KeyError`, `vdf.VDFError`, `py7zr.Bad7zFile`).
   - Log diagnostic events via module-level loggers (`logger = logging.getLogger(__name__)`) using standard severity tiers (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
   - If an optional operation fails (e.g., artwork download or icon extraction), the failure must not abort the primary execution pipeline; the application should log the issue and continue with appropriate default values.

4. **Idempotency in File Transformations:**
   Repeated execution of scanning, shortcut generation, or save synchronization on an unchanged filesystem state must yield identical results without creating duplicate shortcuts in `shortcuts.vdf` or overwriting identical archives.


