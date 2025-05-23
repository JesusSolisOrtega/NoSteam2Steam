# NoSteam2Steam

NoSteam2Steam is a tool designed to manage non-Steam games, allowing users to sync save files, add games to the Steam library, and perform automatic backups. This project is optimized for use on the Steam Deck but can also be used on other platforms with modifications (especially regarding path conversions, which are OS-dependent).

This project relies on **Game Backup Monitor (GBM)** as the primary reference/tool for creating backups on Windows. With some adjustments, it could become a standalone tool, though this falls outside the initial scope of the project.

NoSteam2Steam assumes backups are in the same format as GBM and uses a folder synchronization tool to sync saves between local data and Windows saves. For syncing folders between Windows and the Steam Deck, we chose **Syncthing** (Syncthingy on steamdeck), but any other tool with the same functionality can be used.

## Features

* **Save file synchronization:** Automatically syncs save files across different devices.
* **Non-Steam game management:** Adds games from other platforms (e.g., GOG, Heroic, etc.) to the Steam library.
* **Save file backups:** Creates automatic backups of save files in \`.7z\` format.
* **Lost saves restoration:** Detects and restores lost save files.


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

```bash
git clone https://github.com/JesusSolisOrtega/NoSteam2Steam.git
cd NoSteam2Steam
```

### Install dependencies:

```bash
python3 -m venv venv
```

```bash
source venv/bin/activate
```

```bash
pip install -r requirements.txt
```

## Usage

### Main Menu

Run the main script to access the options menu:

You must run a konsole in the noSteam2Steam folder

```bash
source venv/bin/activate
```

```bash
python noSteam2Steam.py
```

Available options include:

  * **Automatic Sync:** Adds games and syncs save files.
  * **Automatically Add Games to Steam:** Detects and adds non-Steam games.
  * **Manual Save File Sync:** Manually syncs save files.
  * **Manually Add a Game to Steam:** Allows adding specific games.
  * **Reset NoSteam2Steam Configuration:** Clears settings and temporary data.
  * **Enable/Disable Syncthing:** Manages the background sync service.
  * **Change Synced Game Folders:** Modifies folders where games and saves are searched.
  * **Exit:** Closes the application.


### Technical Overview (Brief Explanation)

The program consists of three (actually four) main modules, each handling a specific task: 

1. Game Identification: Searches the designated sync folder for game executables and supplements this with Lutris data.

2. Steam Integration: Adds games to Steam, associates images, and calculates game IDs (necessary for syncing).

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
