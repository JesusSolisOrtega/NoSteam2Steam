"""XDG Desktop Entry management and system launcher integration for Linux & SteamOS."""

import logging
from pathlib import Path
import stat
import sys

logger = logging.getLogger(__name__)


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
    """Installs .desktop launcher into ~/.local/share/applications and ~/Desktop."""
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
            desktop_dir = Path.home() / "Desktop"
            if desktop_dir.exists():
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
    """Removes .desktop entries from ~/.local/share/applications and ~/Desktop."""
    success = True
    for path in [
        Path.home() / ".local" / "share" / "applications" / "nosteam2steam.desktop",
        Path.home() / "Desktop" / "nosteam2steam.desktop",
    ]:
        if path.exists():
            try:
                path.unlink()
                logger.info(f"Removed desktop entry: {path}")
            except OSError as e:
                logger.error(f"Failed removing {path}: {e}")
                success = False
    return success


__all__ = ["get_desktop_entry_content", "install_desktop_entry", "uninstall_desktop_entry"]

