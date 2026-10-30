"""Main application orchestration module for NoSteam2Steam."""

import argparse
import logging
import sys

# Verify dependencies before importing project modules
missing_deps = []
for mod in ["vdf", "py7zr", "requests", "yaml"]:
    try:
        __import__(mod)
    except ImportError:
        missing_deps.append(mod)

if missing_deps:
    msg = (
        f"Missing required Python packages: {', '.join(missing_deps)}.\n"
        "Please run via launch.sh or install requirements.txt into your environment."
    )
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)

from nosteam2steam import ui
from nosteam2steam.i18n import _, select_language_dialog, set_language
from nosteam2steam.steam import shortcuts
from nosteam2steam.backup import manager as backup_manager, run_sync
from nosteam2steam.desktop import install_desktop_entry, manage_desktop_shortcut, uninstall_desktop_entry
from nosteam2steam.identification import manual_adder
from nosteam2steam.identification import data_manager
from nosteam2steam.utils import manage_sync_folders, show_cleanup_dialog, manage_syncthingy_service

logger = logging.getLogger(__name__)


def parse_arguments(argv=None):
    """Parses optional command-line arguments for headless non-interactive operation."""
    parser = argparse.ArgumentParser(
        prog="nosteam2steam",
        description="Non-Steam game manager and save game synchronization tool for Linux & SteamOS.",
    )
    parser.add_argument(
        "--sync",
        "--auto",
        action="store_true",
        help="Run full automated pipeline: discover games, add to Steam, and sync save files.",
    )
    parser.add_argument(
        "--add-games",
        action="store_true",
        help="Discover games and update Steam shortcuts without syncing saves.",
    )
    parser.add_argument(
        "--sync-saves",
        action="store_true",
        help="Synchronize save files with the backup folder without scanning for new games.",
    )
    parser.add_argument(
        "--clean-config",
        action="store_true",
        help="Clear detected games configuration non-interactively.",
    )
    parser.add_argument(
        "--install-desktop",
        action="store_true",
        help="Install standard XDG desktop entry to application launcher and desktop.",
    )
    parser.add_argument(
        "--uninstall-desktop",
        action="store_true",
        help="Remove installed XDG desktop entries.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress graphical dialog notifications and progress prompts.",
    )
    parser.add_argument(
        "--lang",
        "--language",
        type=str,
        help="Specify interface language code (e.g. en, es, gl, eu, ca, de, fr, it, pt, ru, tr, ko, ar, id, sw, hi, ur, zh, ja).",
    )
    return parser.parse_args(argv)


def show_main_menu():
    menu_items = [
        ("1", _("Automatic sync (add games and sync saves)")),
        ("2", _("Add games to Steam automatically")),
        ("3", _("Game saves synchronization")),
        ("4", _("Manually add a game to Steam")),
        ("5", _("Clean NoSteam2Steam configuration")),
        ("6", _("Enable/disable Syncthing")),
        ("7", _("Enable/disable Desktop shortcut")),
        ("8", _("Change synchronized game folders")),
        ("9", _("Change interface language")),
        ("10", _("Exit")),
    ]
    return ui.show_menu(
        title=_("NoSteam2Steam - Non-Steam Games Management"),
        text=_('Select an option:\n<span foreground="red">Note: Steam needs restart after adding games</span>'),
        menu_items=menu_items,
        width=650,
        height=460,
    )


def main(argv=None):
    args = parse_arguments(argv)

    if args.lang:
        set_language(args.lang, persist=False)

    # CLI Headless execution
    if args.sync:
        logger.info("Executing automated sync pipeline via CLI...")
        data_manager.main()
        shortcuts.main()
        try:
            run_sync()
        except Exception as e:
            logger.error(f"Sync error: {e}")
        return

    if args.add_games:
        logger.info("Executing game discovery and Steam shortcut addition via CLI...")
        data_manager.main()
        shortcuts.main()
        return

    if args.sync_saves:
        logger.info("Executing save game synchronization via CLI...")
        backup_manager.main()
        return

    if args.clean_config:
        from nosteam2steam.dialogs import delete_current_config

        delete_current_config(game_data=True, saves=False)
        logger.info("Configuration cleared via CLI.")
        return

    if args.install_desktop:
        success = install_desktop_entry()
        print("Desktop entry installation " + ("succeeded." if success else "failed."))
        return

    if args.uninstall_desktop:
        success = uninstall_desktop_entry()
        print("Desktop entry uninstallation " + ("succeeded." if success else "failed."))
        return

    # Interactive GUI mode
    backend = ui.get_dialog_backend()
    if backend == "none":
        logger.error(
            "Error: Neither Zenity nor KDialog is installed on this system.\n"
            "Please install zenity or kdialog, or run NoSteam2Steam with CLI arguments (e.g., --sync, --add-games, --sync-saves)."
        )
        sys.exit(1)

    while True:
        option = show_main_menu()

        if not option or option == "10":
            break

        if option == "1":
            res_ident = data_manager.main() or {}
            res_shortcuts = shortcuts.main() or {}
            res_sync = {}
            try:
                res_sync = run_sync() or {}
            except Exception as e:
                logger.error(f"Sync error: {e}")

            if not args.quiet:
                summary_text = _(
                    "Automatic sync finished successfully:\n\n"
                    "• Identified titles: {identified}\n"
                    "• Added Steam shortcuts: {added}\n"
                    "• Updated artwork & icons: {updated}\n"
                    "• Synchronized/verified saves: {synced}\n"
                    "• New backups created: {created}\n\n"
                    "Note: If Steam was running, please restart it to display the new games in your library.",
                    identified=res_ident.get("identified", 0),
                    added=res_shortcuts.get("added", 0),
                    updated=res_shortcuts.get("updated", 0),
                    synced=res_sync.get("synced", 0),
                    created=res_sync.get("created", 0),
                )
                ui.show_info(
                    title=_("Synchronization Completed"),
                    text=summary_text,
                    width=460,
                )

        elif option == "2":
            res_ident = data_manager.main() or {}
            res_shortcuts = shortcuts.main() or {}
            if not args.quiet:
                summary_text = _(
                    "Steam shortcut addition finished successfully:\n\n"
                    "• Identified titles: {identified}\n"
                    "• New shortcuts created: {added}\n"
                    "• Updated artwork & icons: {updated}\n\n"
                    "Note: Please restart Steam to display the new shortcuts in your library.",
                    identified=res_ident.get("identified", 0),
                    added=res_shortcuts.get("added", 0),
                    updated=res_shortcuts.get("updated", 0),
                )
                ui.show_info(
                    title=_("Games added to Steam"),
                    text=summary_text,
                    width=440,
                )

        elif option == "3":
            backup_manager.main()

        elif option == "4":
            manual_adder.manual_add_game()

        elif option == "5":
            try:
                show_cleanup_dialog()
            except Exception as e:
                logger.error(f"Error cleaning configuration: {e}")
                continue
        elif option == "6":
            try:
                manage_syncthingy_service()
            except Exception as e:
                logger.error(f"Error: {e}")
                continue

        elif option == "7":
            try:
                manage_desktop_shortcut()
            except Exception as e:
                logger.error(f"Error managing desktop shortcut: {e}")
                continue

        elif option == "8":
            try:
                manage_sync_folders()
            except Exception as e:
                logger.error(f"Error: {e}")
                continue

        elif option == "9":
            select_language_dialog()


if __name__ == "__main__":
    main()
