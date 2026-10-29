"""Test suite package for NoSteam2Steam."""

import os
import subprocess
import sys
from unittest.mock import MagicMock

# Strip display variables to isolate test executions from graphical display servers
os.environ.pop("DISPLAY", None)
os.environ.pop("WAYLAND_DISPLAY", None)

# Provide mock for py7zr if it is not installed in the test runner environment
if "py7zr" not in sys.modules:
    try:
        import py7zr  # noqa: F401
    except ImportError:
        mock = MagicMock()
        mock.SevenZipFile = MagicMock()
        sys.modules["py7zr"] = mock

# Intercept subprocess invocations of Zenity to prevent GUI dialogs in test runs
_orig_run = subprocess.run
_orig_popen = subprocess.Popen


def _safe_run(*args, **kwargs):
    cmd = args[0] if args else kwargs.get("args", [])
    if isinstance(cmd, (list, tuple)) and cmd and any(t in str(cmd[0]) for t in ("zenity", "kdialog")):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = ""
        mock_res.stderr = ""
        return mock_res
    return _orig_run(*args, **kwargs)


def _safe_popen(*args, **kwargs):
    cmd = args[0] if args else kwargs.get("args", [])
    if isinstance(cmd, (list, tuple)) and cmd and any(t in str(cmd[0]) for t in ("zenity", "kdialog")):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.terminate.return_value = None
        mock_proc.wait.return_value = 0
        return mock_proc
    return _orig_popen(*args, **kwargs)


setattr(subprocess, "run", _safe_run)
setattr(subprocess, "Popen", _safe_popen)

