from __future__ import annotations

import re
from pathlib import PurePosixPath

DRIVE_RE = re.compile(r"^[A-Za-z]:")


def safe_relative_path(path: str) -> PurePosixPath:
    """Validate a relative archive/instance path without normalizing away danger."""

    raw = path.replace("\\", "/")
    if not raw or raw.startswith("/") or DRIVE_RE.match(raw):
        raise ValueError(f"unsafe relative path: {path}")
    posix = PurePosixPath(raw)
    if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
        raise ValueError(f"unsafe relative path: {path}")
    return posix


def safe_file_name(filename: str) -> str:
    """Validate a single file name for mod/cache destinations."""

    posix = safe_relative_path(filename)
    if len(posix.parts) != 1:
        raise ValueError(f"unsafe file name: {filename}")
    return posix.name


def safe_slug(value: str, *, fallback: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in value)
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or fallback

