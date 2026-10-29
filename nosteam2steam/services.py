"""System service management and systemd integration across Linux distributions."""

import logging
from pathlib import Path
import subprocess

import requests

from nosteam2steam.config import SERVICE_FILE
from nosteam2steam.i18n import _
from nosteam2steam import ui

logger = logging.getLogger(__name__)


def get_syncthing_service_name() -> str:
    """Detects whether host distribution uses standard syncthing.service or SteamOS syncthingy.service."""
    for service in ("syncthing.service", "syncthingy.service"):
        if is_service_active(service) or is_service_enabled(service):
            return service

    user_systemd = Path.home() / ".config/systemd/user"
    if (user_systemd / "syncthing.service").exists():
        return "syncthing.service"
    if (user_systemd / "syncthingy.service").exists():
        return "syncthingy.service"

    return "syncthing.service"


def is_service_active(service_name: str = "syncthing.service") -> bool:
    """Checks whether the specified systemd user unit is active."""
    return (
        subprocess.run(
            ["systemctl", "--user", "is-active", service_name],
            capture_output=True,
        ).returncode
        == 0
    )


def is_service_enabled(service_name: str = "syncthing.service") -> bool:
    """Checks whether the specified systemd user unit is enabled."""
    return (
        subprocess.run(
            ["systemctl", "--user", "is-enabled", service_name],
            capture_output=True,
        ).returncode
        == 0
    )


def manage_syncthingy_service() -> bool:
    """
    Displays an interactive Zenity dialog allowing the user to inspect,
    install, activate, or deactivate the background Syncthing/SyncThingy systemd user service.
    """
    service_name = get_syncthing_service_name()

    def is_active():
        return is_service_active(service_name)

    def show_dialog():
        active = is_active()
        display_label = "SyncThingy" if "syncthingy" in service_name else "Syncthing"
        status_text = _("ACTIVE") if active else _("INACTIVE")
        toggle_label = (
            _("Deactivate {service}", service=display_label)
            if active
            else _("Activate {service}", service=display_label)
        )
        return ui.show_radiolist(
            title=_("{service} Service Control", service=display_label),
            text=_(
                "Service: {name}\nStatus: {status}\nSystem restart required for complete application.",
                name=service_name,
                status=status_text,
            ),
            items=[
                (toggle_label, "", True),
                (_("Exit"), "", False),
            ],
            width=380,
            height=250,
        )

    # Check if neither standard syncthing nor Steam Deck syncthingy is present
    user_systemd = Path.home() / ".config/systemd/user"
    has_service = (
        is_service_active(service_name)
        or is_service_enabled(service_name)
        or (user_systemd / service_name).exists()
        or SERVICE_FILE.exists()
    )

    if not has_service:
        install = ui.ask_question(
            title=_("Service Not Found"),
            text=_(
                "Neither Syncthing nor SyncThingy service was detected.\nInstall SyncThingy user service in background?"
            ),
            ok_label=_("Install"),
            cancel_label=_("Cancel"),
        )

        if install:
            try:
                SERVICE_FILE.parent.mkdir(parents=True, exist_ok=True)
                resp = requests.get(
                    "https://raw.githubusercontent.com/zocker-160/SyncThingy/master/linux_packaging/syncthingy.service",
                    timeout=10,
                )
                resp.raise_for_status()
                SERVICE_FILE.write_text(resp.text, encoding="utf-8")
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, timeout=10)
                ui.show_info(
                    title=_("Service Installed"),
                    text=_("Service installed. Run again to manage its state."),
                    timeout=2,
                )
            except Exception as e:
                logger.error(f"Failed to install service: {e}")
                ui.show_error(
                    title=_("Service Error"),
                    text=f"{e}",
                )
        return False

    choice = show_dialog()
    if not choice or choice == _("Exit") or "Exit" in choice:
        return False

    display_label = "SyncThingy" if "syncthingy" in service_name else "Syncthing"
    toggle_pattern = ("Deactivate", "Activate", _("Deactivate {service}", service=display_label), _("Activate {service}", service=display_label))
    if any(pat in choice for pat in toggle_pattern):
        active = is_active()
        try:
            if active:
                subprocess.run(["systemctl", "--user", "stop", service_name], check=True)
                subprocess.run(["systemctl", "--user", "disable", service_name], check=True)
            else:
                subprocess.run(["systemctl", "--user", "enable", service_name], check=True)
                subprocess.run(["systemctl", "--user", "start", service_name], check=True)

            action_text = _("deactivated") if active else _("activated")
            ui.show_info(
                title=_("Service Updated"),
                text=_(
                    "{service} ({name}) {action}.\nRestart recommended.",
                    service=display_label,
                    name=service_name,
                    action=action_text,
                ),
                timeout=2,
            )
            return True
        except subprocess.CalledProcessError:
            ui.show_error(
                title=_("Service Error"),
                text=_("Error changing status for {service}.", service=service_name),
            )

    return False
