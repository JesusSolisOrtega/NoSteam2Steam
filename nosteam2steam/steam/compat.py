"""Steam Proton compatibility configuration manager."""

import os
import logging
from typing import Dict
import vdf

from nosteam2steam.steam.environment import CONFIG_VDF_PATH
from nosteam2steam.atomic import atomic_write

logger = logging.getLogger(__name__)


def set_proton_compat_tools(mapping: Dict[str, str]) -> None:
    """Updates Proton compatibility configuration for multiple games in a single file I/O pass."""
    if not mapping:
        return
    try:
        if not os.path.exists(CONFIG_VDF_PATH):
            logger.error(f"File {CONFIG_VDF_PATH} does not exist.")
            return

        with open(CONFIG_VDF_PATH, "r", encoding="utf-8") as f:
            config_data = vdf.load(f)

        install_cfg = config_data.setdefault("InstallConfigStore", {})
        software = install_cfg.setdefault("Software", {})
        valve = software.setdefault("Valve", {})
        steam = valve.setdefault("Steam", {})
        compat_mapping = steam.setdefault("CompatToolMapping", {})

        for short_appid, compat_tool in mapping.items():
            compat_mapping[str(short_appid)] = {
                "name": compat_tool,
                "config": "",
                "priority": "250",
            }

        with atomic_write(CONFIG_VDF_PATH, mode="w", encoding="utf-8", backup=True) as f:
            vdf.dump(config_data, f, pretty=True)

        logger.info(f"Proton configuration updated for {len(mapping)} games in config.vdf.")
    except Exception as e:
        logger.error(f"Error setting Proton tools in config.vdf: {e}")


def set_proton_compat_tool(short_appid: str, compat_tool: str) -> None:
    set_proton_compat_tools({short_appid: compat_tool})
