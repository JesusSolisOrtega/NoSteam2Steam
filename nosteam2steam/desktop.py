"""XDG Desktop Entry management and system launcher integration for Linux & SteamOS."""

import logging
from pathlib import Path
import stat
import subprocess
import sys

from nosteam2steam import ui
from nosteam2steam.i18n import _

logger = logging.getLogger(__name__)


def get_desktop_dir() -> Path:
    """Returns the user's localized Desktop directory adhering to XDG user dirs."""
    try:
        res = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            p = Path(res.stdout.strip())
            home = Path.home()
            if p.is_dir() and (p == home or home in p.parents):
                return p
    except Exception:
        pass

    for candidate in ["Desktop", "Escritorio", "Schreibtisch", "Bureau"]:
        p = Path.home() / candidate
        if p.is_dir():
            return p
    return Path.home() / "Desktop"


def is_desktop_entry_installed() -> bool:
    """Checks whether the desktop shortcut currently exists in the user's Desktop directory."""
    desktop_file = get_desktop_dir() / "nosteam2steam.desktop"
    return desktop_file.exists()


def get_desktop_entry_content(exec_path: str, icon_path: str) -> str:
    """Generates standard XDG desktop entry specification content."""
    return f"""[Desktop Entry]
Type=Application
Name=NoSteam2Steam
Comment=Non-Steam game manager and save synchronizer for Linux & SteamOS
Exec={exec_path}
Icon={icon_path}
Terminal=false
Categories=Game;Utility;
StartupNotify=true
"""


def install_desktop_entry(target_desktop: bool = True, target_menu: bool = True) -> bool:
    """Installs .desktop launcher into ~/.local/share/applications and the Desktop directory."""
    try:
        repo_root = Path(__file__).resolve().parent.parent
        icon_path = repo_root / "assets" / "icon.png"
        launch_script = repo_root / "launch.sh"

        if launch_script.exists():
            exec_path = str(launch_script)
        else:
            exec_path = f"{sys.executable} {repo_root / 'noSteam2Steam.py'}"

        content = get_desktop_entry_content(exec_path, str(icon_path))
        installed = []

        if target_menu:
            menu_dir = Path.home() / ".local" / "share" / "applications"
            menu_dir.mkdir(parents=True, exist_ok=True)
            menu_file = menu_dir / "nosteam2steam.desktop"
            menu_file.write_text(content, encoding="utf-8")
            menu_file.chmod(menu_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
            installed.append(str(menu_file))

        if target_desktop:
            desktop_dir = get_desktop_dir()
            desktop_dir.mkdir(parents=True, exist_ok=True)
            desktop_file = desktop_dir / "nosteam2steam.desktop"
            desktop_file.write_text(content, encoding="utf-8")
            desktop_file.chmod(desktop_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
            installed.append(str(desktop_file))

        logger.info(f"Desktop entry installed: {', '.join(installed)}")
        return True
    except Exception as e:
        logger.error(f"Failed to install desktop entry: {e}")
        return False


def uninstall_desktop_entry() -> bool:
    """Removes .desktop entries from ~/.local/share/applications and the Desktop directory."""
    success = True
    for path in [
        Path.home() / ".local" / "share" / "applications" / "nosteam2steam.desktop",
        get_desktop_dir() / "nosteam2steam.desktop",
    ]:
        if path.exists():
            try:
                path.unlink()
                logger.info(f"Removed desktop entry: {path}")
            except OSError as e:
                logger.error(f"Failed removing {path}: {e}")
                success = False
    return success


def manage_desktop_shortcut() -> bool:
    """Interactive GUI controller allowing the user to toggle desktop shortcut installation state."""
    is_installed = is_desktop_entry_installed()
    status_label = _("ACTIVE") if is_installed else _("INACTIVE")
    action_label = _("Deactivate") if is_installed else _("Activate")

    confirm = ui.ask_question(
        title=_("Desktop Shortcut Control"),
        text=_(
            "Desktop shortcut status: {status}\n\nDo you want to {action} the desktop shortcut?",
            status=status_label,
            action=action_label.lower(),
        ),
        ok_label=action_label,
        cancel_label=_("Cancel"),
        width=400,
    )
    if not confirm:
        return False

    if is_installed:
        success = uninstall_desktop_entry()
        msg = _("Desktop shortcut successfully deactivated.") if success else _("Failed to remove desktop shortcut.")
    else:
        success = install_desktop_entry(target_desktop=True, target_menu=True)
        msg = _("Desktop shortcut successfully activated.") if success else _("Failed to create desktop shortcut.")

    ui.show_info(title=_("Desktop Shortcut Control"), text=msg, timeout=3)
    return success


__all__ = [
    "get_desktop_dir",
    "is_desktop_entry_installed",
    "get_desktop_entry_content",
    "install_desktop_entry",
    "uninstall_desktop_entry",
    "manage_desktop_shortcut",
]

