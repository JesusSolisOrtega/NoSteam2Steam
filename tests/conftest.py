"""Common test fixtures and mocks for the test suite."""

import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest

# Gracefully provide a mock for py7zr if it is not installed in the test environment
if "py7zr" not in sys.modules:
    try:
        import py7zr  # noqa: F401
    except ImportError:
        mock_py7zr = MagicMock()
        mock_py7zr.SevenZipFile = MagicMock()
        sys.modules["py7zr"] = mock_py7zr


@pytest.fixture(autouse=True)
def prevent_zenity_gui_in_tests():
    """Globally intercepts any subprocess call to Zenity, preventing GUI windows during tests."""
    orig_run = subprocess.run
    orig_popen = subprocess.Popen

    def safe_run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if isinstance(cmd, (list, tuple)) and cmd and any(t in str(cmd[0]) for t in ("zenity", "kdialog")):
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = ""
            mock_res.stderr = ""
            return mock_res
        return orig_run(*args, **kwargs)

    def safe_popen(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if isinstance(cmd, (list, tuple)) and cmd and any(t in str(cmd[0]) for t in ("zenity", "kdialog")):
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.stdin = MagicMock()
            mock_proc.terminate.return_value = None
            mock_proc.wait.return_value = 0
            return mock_proc
        return orig_popen(*args, **kwargs)

    with patch("subprocess.run", side_effect=safe_run), patch("subprocess.Popen", side_effect=safe_popen):
        yield
