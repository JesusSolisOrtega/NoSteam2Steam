# NoSteam2Steam

**NoSteam2Steam** is a tool designed to manage non-Steam games by allowing users to:

* Automatically detect and add non-Steam games to the Steam library (with artwork, icons, and the best available compatibility tool)

* Sync and back up save files

* Restore lost saves from previously added games

While it's optimized for the **Steam Deck**, it can also be used on other platforms with some adjustments—particularly related to OS-specific path conversions.

This project uses **Game Backup Monitor (GBM)** as the main reference/tool for creating backups on Windows. However, **NoSteam2Steam** can be used as a standalone tool on the Steam Deck.

Backups are expected to follow the same folder structure as GBM. To sync save files between local Steam Deck data and Windows saves, we use **Syncthing** (known as Syncthingy on the Steam Deck). That said, any folder synchronization tool with similar functionality can be used.

If you’re only interested in:

* Adding non-Steam games to Steam with artwork, or

* Backing up and restoring save files locally on the Steam Deck, including restoring saves from previously added games

...then **NoSteam2Steam** can handle it all on its own — no additional tools required.

## Features

* **Save file synchronization:** Automatically syncs save files in the backups folder.
* **Non-Steam game management:** Adds games from other platforms (e.g., GOG, Heroic, etc.) to the Steam library.
* **Save file backups:** Creates automatic backups of save files in \`.7z\` format.
* **Lost saves restoration:** Detects and restores lost save files.
* **Compatibility tool auto-selection**: Automatically chooses the best available compatibility layer (e.g., Proton-ge) based on your system setup.

### Dependencies:

* Python 3.11 or higher
* `py7zr` for `.7z` file manipulation
* `zenity` for the graphical user interface
* `requests` for external API queries
* `vdf` for handling Steam configuration files

### Supported OS:

* Steam Deck (Linux)
* Other Linux distributions (untested/may require minor adjustments)

## Installation

### Clone the repository:

Using the Terminal:

```bash
git clone https://github.com/JesusSolisOrtega/NoSteam2Steam.git
cd NoSteam2Steam
```

Alternatively, you can simply download the `.zip` and extract it

### Installation:

* You may need to activate developer mode. In game mode -> settings -> system -> developer mode.

Double click on the `installer.sh` file to install noSteam2Steam

If, for any reason, it doesn’t run, open a terminal and run it manually:

```bash
bash installer.sh
```

## Usage

### Main Menu

**Run the shortcut to access the options menu**

**Important**: After adding games with NoSteam2Steam, you need to restart Steam for it to recognize the changes and properly show the new games.

Available options include:

  * **Automatic Sync:** Adds games and syncs save files.
  * **Automatically Add Games to Steam:** Detects and adds non-Steam games.
  * **Game saves synchronization:** Options to sync save files (sync gamesaves/restore old saves).
  * **Manually Add a Game to Steam:** Allows adding specific games.
  * **Reset NoSteam2Steam Configuration:** Clears settings and temporary data.
  * **Enable/Disable Syncthing:** Manages the background sync service.
  * **Change Synced Game Folders:** Modifies folders where games and saves are searched.
  * **Exit:** Closes the application.


### Technical Overview (Brief Explanation)

The program consists of three (actually four) main modules, each handling a specific task: 

1. Game Identification: Searches the designated sync folder for game executables and supplements this with Lutris data. It also auto-select the best available launcher if it have x86, x64 and/or Vulkan executables.

2. Steam Integration: Steam Integration: Adds games to Steam, associates images, calculates game IDs, and automatically selects the most suitable compatibility tool available on the system.

3. Save File Sync: The core feature—reads backups from the designated folder and syncs them with local save files of Steam-added games. It relies on the backup structure from Game Backup Monitor (GBM) and configuration files from GBM and Ludusavi.

*The fourth module is manual game detection, which functions similarly to the first module but allows user selection and overwrites previous entries if a game was already associated with an executable. Automatic detection respects manual selections.

*Additional functionalities include resetting configurations for troubleshooting or clean setups. The program prioritizes reliability (e.g., avoiding overwriting saves if uncertain) while minimizing user prompts for efficiency. Once a file is synced or manually entered, it assumes this behavior for future runs.

Both the first and second modules update data if changes are detected (except for images, which are not redownloaded once found).

Most menu options are self-explanatory:

1. Automatic Sync → Full process: identifies, adds, and syncs saves.

2. Automatically Add Games to Steam → Runs the first two modules (identification + Steam integration).

3. Manual Save Sync → Syncs saves.

4. Reset Configuration → Options to clear game/sync settings.

5. Enable/Disable Syncthing → Toggles Syncthing for sync folder management in Steam Game Mode (Note: Syncthing works well for saves but struggles with large game files—consider alternatives for game transfers).

6. Change Synced Game Folders → Adjusts folders for synced games (default: $HOME/games).


** Based on tests, SyncThing works well for backups of saved games, but it has caused problems with games for large files, so other methods or programs are recommended to transfer games to the device from Windows (or do it manually).

## Credits & References

Key projects used as references for game/save file identification:

* **GBM** -> https://mikemaximus.github.io/gbm-web/

* **Ludusavi Manifest** -> https://github.com/mtkennerly/ludusavi-manifest

* **Lutris**

Additional repositories for Steam shortcut manipulation and ID calculations:

* Steam Shortcut Manager -> https://github.com/CorporalQuesadilla/Steam-Shortcut-Manager

* Heroic Games Launcher -> https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher/tree/main

* SteamGridDB -> https://github.com/SteamGridDB/steam-rom-manager/blob/master/src/lib/helpers/steam/generate-app-id.ts


## Contributions

Contributions are welcome! To collaborate:

1.  Fork the repository.
2.  Create a branch for your feature/fix.
3.  Commit your changes.
4.  Submit a pull request.

## License

Copyright (c) 2025 Jesús Solís Ortega

This software is distributed for **educational and personal use only**.
**Commercial use**, distribution, sublicensing, sale, or integration into for-profit products/services is **prohibited** without the copyright holder's consent.
Non-commercial use, copying, and modification are permitted, provided this copyright notice remains intact.

For commercial inquiries, contact the author.

**NO WARRANTIES, EXPRESS OR IMPLIED, ARE PROVIDED**.

## Contact

For questions or suggestions, open an issue in the repository or contact me directly.
For commercial integration projects, reach out—I’m likely open to collaboration. Thanks for using NoSteam2Steam!

## Donations

If you find NoSteam2Steam useful and wish to support my work:

* [![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/F1F51F88U3)
* Or donate via [PayPal](https://www.paypal.com/donate/?hosted_button_id=VVRC7ZTVFJWDU)
