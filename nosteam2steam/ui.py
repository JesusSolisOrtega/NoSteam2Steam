import logging
import shutil
import subprocess
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def is_zenity_available() -> bool:
    """Returns True if zenity is available on the system PATH."""
    return shutil.which("zenity") is not None


def is_kdialog_available() -> bool:
    """Returns True if kdialog is available on the system PATH."""
    return shutil.which("kdialog") is not None


def get_dialog_backend() -> str:
    """Returns 'zenity' if available, falls back to 'kdialog', or 'none' if headless/unavailable."""
    if is_zenity_available():
        return "zenity"
    if is_kdialog_available():
        return "kdialog"
    return "none"


def show_info(title: str, text: str, timeout: Optional[int] = None, width: int = 300) -> bool:
    backend = get_dialog_backend()
    if backend == "kdialog":
        cmd = ["kdialog", f"--title={title}", f"--msgbox={text}"]
    else:
        cmd = ["zenity", "--info", f"--title={title}", f"--text={text}", f"--width={width}"]
        if timeout:
            cmd.append(f"--timeout={timeout}")
    try:
        subprocess.run(cmd, check=False)
        return True
    except Exception as e:
        logger.error(f"Error displaying info dialog: {e}")
        return False


def show_error(title: str, text: str, width: int = 350) -> bool:
    backend = get_dialog_backend()
    if backend == "kdialog":
        cmd = ["kdialog", f"--title={title}", f"--error={text}"]
    else:
        cmd = ["zenity", "--error", f"--title={title}", f"--text={text}", f"--width={width}"]
    try:
        subprocess.run(cmd, check=False)
        return True
    except Exception as e:
        logger.error(f"Error displaying error dialog: {e}")
        return False


def show_warning(title: str, text: str, width: int = 350) -> bool:
    backend = get_dialog_backend()
    if backend == "kdialog":
        cmd = ["kdialog", f"--title={title}", f"--sorry={text}"]
    else:
        cmd = ["zenity", "--warning", f"--title={title}", f"--text={text}", f"--width={width}"]
    try:
        subprocess.run(cmd, check=False)
        return True
    except Exception as e:
        logger.error(f"Error displaying warning dialog: {e}")
        return False


def ask_question(
    title: str, text: str, ok_label: Optional[str] = None, cancel_label: Optional[str] = None, width: int = 350
) -> bool:
    backend = get_dialog_backend()
    if backend == "kdialog":
        cmd = ["kdialog", f"--title={title}", f"--yesno={text}"]
        if ok_label:
            cmd.append(f"--yes-label={ok_label}")
        if cancel_label:
            cmd.append(f"--no-label={cancel_label}")
    else:
        cmd = ["zenity", "--question", f"--title={title}", f"--text={text}", f"--width={width}"]
        if ok_label:
            cmd.append(f"--ok-label={ok_label}")
        if cancel_label:
            cmd.append(f"--cancel-label={cancel_label}")
    try:
        res = subprocess.run(cmd, check=False)
        return res.returncode == 0
    except Exception as e:
        logger.error(f"Error displaying question dialog: {e}")
        return False


def show_entry(title: str, text: str, default: str = "") -> Optional[str]:
    backend = get_dialog_backend()
    if backend == "kdialog":
        cmd = ["kdialog", f"--title={title}", f"--inputbox={text}", default]
    else:
        cmd = ["zenity", "--entry", f"--title={title}", f"--text={text}", f"--entry-text={default}"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return res.stdout.strip()
        return None
    except Exception as e:
        logger.error(f"Error displaying text entry dialog: {e}")
        return None


def select_path(
    title: str = "Select Path", directory: bool = False, file_filter: Optional[str] = None
) -> Optional[str]:
    backend = get_dialog_backend()
    if backend == "kdialog":
        cmd = ["kdialog", f"--title={title}"]
        if directory:
            cmd.append("--getexistingdirectory")
        else:
            cmd.append("--getopenfilename")
    else:
        cmd = ["zenity", "--file-selection", f"--title={title}"]
        if directory:
            cmd.append("--directory")
        if file_filter:
            cmd.append(f"--file-filter={file_filter}")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
        return None
    except Exception as e:
        logger.error(f"Error displaying file selection dialog: {e}")
        return None


def show_menu(
    title: str,
    text: str,
    menu_items: List[Tuple[str, str]],
    width: int = 650,
    height: int = 400,
    hide_header: bool = False,
    cancel_label: Optional[str] = None,
) -> Optional[str]:
    backend = get_dialog_backend()
    if backend == "kdialog":
        flat_items = []
        for opt, desc in menu_items:
            flat_items.extend([opt, desc if desc else opt])
        cmd = ["kdialog", f"--title={title}", f"--menu={text}"] + flat_items
    else:
        flat_items = []
        for opt, desc in menu_items:
            flat_items.append(opt)
            if desc:
                flat_items.append(desc)
        columns = ["--column=Option"]
        if any(desc for _, desc in menu_items):
            columns.append("--column=Description")

        cmd = [
            "zenity",
            "--list",
            f"--title={title}",
            f"--text={text}",
            f"--width={width}",
            f"--height={height}",
        ] + columns
        if hide_header:
            cmd.append("--hide-header")
        if cancel_label:
            cmd.append(f"--cancel-label={cancel_label}")
        cmd.extend(flat_items)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return res.stdout.strip()
        return None
    except Exception as e:
        logger.error(f"Error displaying menu dialog: {e}")
        return None


def show_checklist(
    title: str,
    text: str,
    items: List[Tuple[str, bool]],
    column_name: str = "Folder",
    width: int = 500,
    height: int = 350,
) -> List[str]:
    """Displays a checklist dialog and returns the list of checked item labels."""
    backend = get_dialog_backend()
    if backend == "kdialog":
        flat_items = []
        for item, checked in items:
            flat_items.extend([item, item, "on" if checked else "off"])
        cmd = ["kdialog", f"--title={title}", f"--checklist={text}"] + flat_items
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0 and res.stdout.strip():
                # kdialog returns space-separated or quoted items
                out = res.stdout.strip().replace('"', "")
                return [line.strip() for line in out.split() if line.strip()]
            return []
        except Exception as e:
            logger.error(f"Error displaying checklist dialog via kdialog: {e}")
            return []

    formatted_input = "\n".join([f"{'TRUE' if checked else 'FALSE'}\n{item}" for item, checked in items])
    cmd = [
        "zenity",
        "--list",
        f"--title={title}",
        f"--text={text}",
        "--column=Selection",
        f"--column={column_name}",
        "--checklist",
        "--separator=\n",
        "--multiple",
        f"--width={width}",
        f"--height={height}",
    ]
    try:
        res = subprocess.run(cmd, input=formatted_input, capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return [line for line in res.stdout.strip().split("\n") if line]
        return []
    except Exception as e:
        logger.error(f"Error displaying checklist dialog: {e}")
        return []


def show_radiolist(
    title: str,
    text: str,
    items: List[Tuple[str, str, bool]],
    width: int = 350,
    height: int = 250,
) -> Optional[str]:
    """Displays a single-selection radiolist dialog and returns the selected option."""
    backend = get_dialog_backend()
    if backend == "kdialog":
        flat_items = []
        for tag, desc, checked in items:
            flat_items.extend([tag, desc, "on" if checked else "off"])
        cmd = ["kdialog", f"--title={title}", f"--radiolist={text}"] + flat_items
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().replace('"', "")
            return None
        except Exception as e:
            logger.error(f"Error displaying radiolist dialog via kdialog: {e}")
            return None

    flat_items = []
    for tag, desc, checked in items:
        flat_items.extend(["TRUE" if checked else "FALSE", tag, desc])
    cmd = [
        "zenity",
        "--list",
        "--radiolist",
        f"--title={title}",
        f"--text={text}",
        "--column=Select",
        "--column=Option",
        "--column=Description",
        f"--width={width}",
        f"--height={height}",
    ] + flat_items
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
        return None
    except Exception as e:
        logger.error(f"Error displaying radiolist dialog: {e}")
        return None


class ProgressDialog:
    """Context manager for responsive modal progress dialog with dynamic text updates."""

    def __init__(
        self,
        title: str,
        text: str = "Processing...",
        pulsate: bool = True,
        width: int = 350,
    ) -> None:
        self.title = title
        self.text = text
        self.pulsate = pulsate
        self.width = width
        self.backend = get_dialog_backend()
        self.process: Optional[subprocess.Popen] = None

    def __enter__(self) -> "ProgressDialog":
        if self.backend == "zenity":
            cmd = [
                "zenity",
                "--progress",
                f"--title={self.title}",
                f"--text={self.text}",
                "--no-cancel",
                f"--width={self.width}",
            ]
            if self.pulsate:
                cmd.append("--pulsate")
            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
            except Exception as e:
                logger.error(f"Failed to start Zenity progress dialog: {e}")
                self.process = None
        elif self.backend == "kdialog":
            try:
                self.process = subprocess.Popen(
                    ["kdialog", f"--title={self.title}", f"--passivepopup={self.text}", "10"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                logger.error(f"Failed to start KDialog notification: {e}")
                self.process = None
        else:
            logger.info(f"[{self.title}] {self.text}")
        return self

    def update(self, text: str, percentage: Optional[int] = None) -> None:
        """Dynamically updates the displayed status message and optional percentage."""
        self.text = text
        logger.info(f"[{self.title}] {text}")
        if self.process and self.process.poll() is None:
            if self.backend == "zenity" and self.process.stdin:
                try:
                    if percentage is not None:
                        self.process.stdin.write(f"{percentage}\n")
                    self.process.stdin.write(f"# {text}\n")
                    self.process.stdin.flush()
                except (IOError, BrokenPipeError):
                    pass

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.process:
            try:
                if self.process.stdin and not self.process.stdin.closed:
                    self.process.stdin.close()
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None


def progress_dialog(
    title: str,
    text: str = "Processing...",
    pulsate: bool = True,
    width: int = 350,
) -> ProgressDialog:
    """Returns a ProgressDialog context manager for real-time operation feedback."""
    return ProgressDialog(title=title, text=text, pulsate=pulsate, width=width)
