from __future__ import annotations

from pathlib import Path
import os
import tempfile
from typing import Callable


def atomic_write(path: str | Path, write_fn: Callable[[Path], None]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        write_fn(tmp_path)
        os.replace(tmp_path, target)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        finally:
            raise
