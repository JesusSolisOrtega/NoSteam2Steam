"""Interactive conflict resolution and backup disambiguation dialogs."""

import logging
import subprocess

from nosteam2steam import ui

logger = logging.getLogger(__name__)


def show_backup_selection_dialog(backups_info):
    """
    Displays a Zenity radiolist dialog allowing the user to disambiguate
    between multiple existing backups for the same target save path.
    """
    try:
        if not backups_info:
            return -1

        items = []
        default_option = 0

        for i, backup in enumerate(backups_info):
            is_recent = backup.get("most_recent", False)
            recent_text = " (MOST RECENT)" if is_recent else ""

            backup_text = (
                f"File: {backup['file'].name}{recent_text} | "
                f"Folder: {backup['folder']} | "
                f"Original: {backup['original_path']} | "
                f"Date: {backup['modification_date']}"
            )

            items.append((str(i), backup_text.replace('"', "'"), is_recent))
            if is_recent:
                default_option = i

        choice = ui.show_radiolist(
            title="Backup Selection",
            text="Multiple backups found for the same path. Select which one to keep:",
            items=items,
            width=800,
            height=600,
        )

        if choice is None:
            return -1

        return int(choice) if choice.isdigit() else default_option

    except Exception as e:
        logger.error(f"Error in backup selection dialog: {e}")
        ui.show_error(title="Error", text=f"Error selecting backup: {str(e)}")
        return -1


def show_sync_conflict_dialog(
    game_name,
    backup_date,
    steamdeck_date,
    hash_backup,
    hash_local,
    hash_backup_record,
    hash_local_record,
):
    """
    Displays an interactive Zenity dialog detailing timestamp and SHA-256 hash
    discrepancies, prompting the user to choose between local or backup state.
    """
    try:
        if backup_date > steamdeck_date:
            text_backup = f"Backup (newer: {backup_date.strftime('%Y-%m-%d %H:%M:%S')}"
            text_local = f"Local save (older: {steamdeck_date.strftime('%Y-%m-%d %H:%M:%S')}"
        elif steamdeck_date > backup_date:
            text_backup = f"Backup (older: {backup_date.strftime('%Y-%m-%d %H:%M:%S')}"
            text_local = f"Local save (newer: {steamdeck_date.strftime('%Y-%m-%d %H:%M:%S')})"
        else:
            text_backup = f"Backup (same date: {backup_date.strftime('%Y-%m-%d %H:%M:%S')})"
            text_local = f"Local save (same date: {steamdeck_date.strftime('%Y-%m-%d %H:%M:%S')})"

        changes_backup = " (changes)" if hash_backup != hash_backup_record else " (same)"
        changes_local = " (changes)" if hash_local != hash_local_record else " (same)"

        additional_message = ""
        if hash_backup_record is None or hash_local_record is None:
            additional_message = "\n\n⚠️ No previous sync record exists for this game."

        message = (
            f"Changes detected in save files for:\n"
            f"<b>{game_name}</b>{additional_message}\n\n"
            f"<b>Which file do you want to preserve?</b>\n\n"
            f"<b>1. {text_backup}</b>\n"
            f"<b>2. {text_local}</b>\n\n"
            f"Backup files (hash): {changes_backup}\n"
            f"Local files (hash): {changes_local}"
        )

        cmd = [
            "zenity",
            "--question",
            "--title=Save Game Sync",
            f"--text={message}",
            "--ok-label=Use Backup (1)",
            "--cancel-label=Use Local (2)",
            "--extra-button=Cancel",
            "--width=700",
            "--height=400",
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.stderr.strip() == "Cancel":
            return "cancel"
        elif result.returncode == 0:
            return "backup"
        else:
            return "local"

    except Exception as e:
        logger.error(f"Error in conflict dialog: {e}")
        ui.show_error(title="Error", text=f"Error showing conflict dialog: {str(e)}")
        return "cancel"
