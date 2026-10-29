"""System service management and systemd integration across Linux distributions."""

from pathlib import Path
import subprocess
from nosteam2steam.config import SERVICE_FILE
from nosteam2steam import ui


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
        return ui.show_radiolist(
            title=f"{display_label} Control",
            text=f"Service: {service_name}\nStatus: {'ACTIVE' if active else 'INACTIVE'}\nRestart required for full changes",
            items=[
                (f"{'Deactivate' if active else 'Activate'} {display_label}", "", True),
                ("Exit", "", False),
            ],
            width=350,
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
            title="Service Not Found",
            text="Neither Syncthing nor SyncThingy service was detected.\nInstall SyncThingy in background?",
            ok_label="Install",
            cancel_label="Cancel",
        )

        if install:
            SERVICE_FILE.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "wget",
                    "-qO",
                    str(SERVICE_FILE),
                    "https://raw.githubusercontent.com/zocker-160/SyncThingy/master/linux_packaging/syncthingy.service",
                ],
                check=True,
            )
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            ui.show_info(title="Service Installed", text="Service installed. Run again to control.", timeout=2)
        return False

    choice = show_dialog()
    if not choice or "Exit" in choice:
        return False

    if "Activate" in choice or "Deactivate" in choice:
        active = is_active()
        display_label = "SyncThingy" if "syncthingy" in service_name else "Syncthing"
        try:
            if active:
                subprocess.run(["systemctl", "--user", "stop", service_name], check=True)
                subprocess.run(["systemctl", "--user", "disable", service_name], check=True)
            else:
                subprocess.run(["systemctl", "--user", "enable", service_name], check=True)
                subprocess.run(["systemctl", "--user", "start", service_name], check=True)

            ui.show_info(
                title="Service Updated",
                text=f"{display_label} ({service_name}) {'activated' if not active else 'deactivated'}.\nRestart recommended.",
                timeout=2,
            )
            return True
        except subprocess.CalledProcessError:
            ui.show_error(title="Service Error", text=f"Error changing status for {service_name}")

    return False
