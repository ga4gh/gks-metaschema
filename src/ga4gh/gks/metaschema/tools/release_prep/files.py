"""Atomic text-file writes used by release-preparation mutations."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_text_atomically(file_path: Path, text: str) -> None:
    """Replace a text file only after its complete replacement is written.

    The temporary file is created beside ``file_path`` so replacement remains
    atomic on the same filesystem. The destination file mode is retained.

    :param file_path: Existing destination file to replace.
    :param text: Complete replacement text.
    """
    file_mode = file_path.stat().st_mode
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{file_path.name}.", dir=file_path.parent, text=True
    )
    temp_path = Path(temp_name)
    try:
        os.fchmod(temp_fd, file_mode)
        with os.fdopen(temp_fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temp_path.replace(file_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
