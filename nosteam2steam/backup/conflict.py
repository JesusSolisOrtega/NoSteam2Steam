"""Interactive conflict resolution and backup disambiguation dialogs."""

import logging
import subprocess

from nosteam2steam import ui
from nosteam2steam.i18n import _

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
            recent_text = _(" (MOST RECENT)") if is_recent else ""
            reg_text = _(" [REGISTRY]") if backup.get("has_registry") else ""

            size_bytes = backup.get("size_bytes", 0)
            if size_bytes >= 1024 * 1024:
                size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
            elif size_bytes >= 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            elif size_bytes > 0:
                size_str = f"{size_bytes} B"
            else:
                size_str = ""
            size_part = f" | {_('Size')}: {size_str}" if size_str else ""

            backup_text = (
                f"{backup['file'].name}{recent_text}{reg_text}{size_part} | "
                f"{_('Folder')}: {backup['folder']} | "
                f"{_('Date')}: {backup['modification_date']} | "
                f"{_('Path')}: {backup['original_path']}"
            )

            items.append((str(i), backup_text.replace('"', "'"), is_recent))
            if is_recent:
                default_option = i

        choice = ui.show_radiolist(
            title=_("Backup Selection"),
            text=_("Multiple backups found for the same path. Select which one to keep:"),
            items=items,
            width=800,
            height=600,
        )

        if choice is None:
            return -1

        return int(choice) if choice.isdigit() else default_option

    except Exception as e:
        logger.error(f"Error in backup selection dialog: {e}")
        ui.show_error(title=_("Error"), text=_("Error selecting backup: {error}", error=str(e)))
        return -1


def show_sync_conflict_dialog(
    game_name,
    backup_date,
    steamdeck_date,
    hash_backup,
    hash_local,
    hash_backup_record,
    hash_local_record,
    last_action=None,
    last_sync_date=None,
):
    """
    Displays an interactive Zenity dialog detailing timestamp, transfer direction, and SHA-256 hash
    discrepancies, prompting the user to choose between local or backup state.
    """
    try:
        b_date_str = backup_date.strftime("%Y-%m-%d %H:%M:%S")
        s_date_str = steamdeck_date.strftime("%Y-%m-%d %H:%M:%S")
        if backup_date > steamdeck_date:
            text_backup = _("Backup (newer: {date})", date=b_date_str)
            text_local = _("Local save (older: {date})", date=s_date_str)
        elif steamdeck_date > backup_date:
            text_backup = _("Backup (older: {date})", date=b_date_str)
            text_local = _("Local save (newer: {date})", date=s_date_str)
        else:
            text_backup = _("Backup (same date: {date})", date=b_date_str)
            text_local = _("Local save (same date: {date})", date=s_date_str)

        changes_backup = _(" (changes)") if hash_backup != hash_backup_record else _(" (same)")
        changes_local = _(" (changes)") if hash_local != hash_local_record else _(" (same)")

        transfer_info = ""
        if last_action:
            if last_action == "local":
                dir_desc = _("Local save -> Backup repository")
            elif last_action == "backup":
                dir_desc = _("Backup repository -> Local save")
            else:
                dir_desc = str(last_action)
            date_str = f" ({last_sync_date})" if last_sync_date else ""
            transfer_info = f"\n\n<b>{_('Last synchronization transfer')}:</b>\n• {_('Direction')}: {dir_desc}{date_str}"

        additional_message = ""
        if hash_backup_record is None or hash_local_record is None:
            additional_message = "\n\n⚠️ " + _("No previous sync record exists for this game.")

        header = _("Changes detected in save files for:\n<b>{game}</b>", game=game_name)
        prompt_q = _("Which file do you want to preserve?")
        label_backup_hash = _("Backup files (hash): {status}", status=changes_backup)
        label_local_hash = _("Local files (hash): {status}", status=changes_local)

        message = (
            f"{header}{additional_message}{transfer_info}\n\n"
            f"<b>{prompt_q}</b>\n\n"
            f"<b>1. {text_backup}</b>\n"
            f"<b>2. {text_local}</b>\n\n"
            f"{label_backup_hash}\n"
            f"{label_local_hash}"
        )

        backend = ui.get_dialog_backend()
        if backend == "kdialog":
            cmd = [
                "kdialog",
                f"--title={_('Save Game Conflict')}",
                f"--warningyesnocancel={message}",
                f"--yes-label={_('Use Backup (1)')}",
                f"--no-label={_('Use Local (2)')}",
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode == 0:
                return "backup"
            elif result.returncode == 1:
                return "local"
            else:
                return "cancel"

        cmd = [
            "zenity",
            "--question",
            f"--title={_('Save Game Conflict')}",
            f"--text={message}",
            f"--ok-label={_('Use Backup (1)')}",
            f"--cancel-label={_('Use Local (2)')}",
            f"--extra-button={_('Cancel')}",
            "--width=700",
            "--height=400",
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        cancel_text = _("Cancel")
        if result.stderr.strip() in (cancel_text, "Cancel"):
            return "cancel"
        elif result.returncode == 0:
            return "backup"
        else:
            return "local"

    except Exception as e:
        logger.error(f"Error in conflict dialog: {e}")
        ui.show_error(title=_("Error"), text=_("Error showing conflict dialog: {error}", error=str(e)))
        return "cancel"
