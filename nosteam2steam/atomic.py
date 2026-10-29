"""Atomic persistence utilities guaranteeing POSIX ACID file updates."""

from contextlib import contextmanager
import logging
import os
from pathlib import Path
import shutil
from typing import Any, Generator, IO, Optional, Union
import uuid

logger = logging.getLogger(__name__)


@contextmanager
def atomic_write(
    file_path: Union[str, Path],
    mode: str = "w",
    encoding: Optional[str] = "utf-8",
    backup: bool = False,
) -> Generator[IO[Any], None, None]:
    """
    Context manager providing POSIX atomic file persistence.

    1. Stages writes to a temporary file within the same directory/mount point.
    2. Flushes user-space buffers and invokes os.fsync to commit bytes to physical storage.
    3. Optionally creates a .bak snapshot of the pre-existing target file.
    4. Atomically replaces target via os.replace (POSIX rename(2) syscall).
    5. On unhandled exception, unlinks staged temporary file and leaves target untouched.
    """
    path = Path(file_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_name(f".{path.name}.tmp_{uuid.uuid4().hex[:8]}")

    open_kwargs: dict[str, Any] = {}
    if "b" not in mode:
        open_kwargs["encoding"] = encoding

    f = open(temp_file, mode, **open_kwargs)
    try:
        yield f
        f.flush()
        os.fsync(f.fileno())
        f.close()

        if backup and path.exists():
            bak_path = path.with_name(f"{path.name}.bak")
            try:
                shutil.copy2(path, bak_path)
            except OSError as be:
                logger.warning(f"Could not create backup snapshot {bak_path}: {be}")

        os.replace(temp_file, path)
    except Exception:
        if not f.closed:
            f.close()
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
        raise


__all__ = ["atomic_write"]

