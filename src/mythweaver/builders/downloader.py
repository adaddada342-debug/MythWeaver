from __future__ import annotations

import asyncio
import hashlib
import os
import urllib.request
from pathlib import Path

from mythweaver.schemas.contracts import ModFile


def _hash_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file_hashes(path: Path, expected_hashes: dict[str, str]) -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    checked = False
    for algorithm in ("sha1", "sha512"):
        expected = expected_hashes.get(algorithm)
        if not expected:
            continue
        checked = True
        if _hash_file(path, algorithm) != expected.lower():
            return False
    return checked


def _download(url: str, destination: Path, user_agent: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = destination.with_suffix(destination.suffix + ".part")
        with tmp_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        os.replace(tmp_path, destination)


async def download_mod_file(
    file: ModFile,
    destination: Path,
    user_agent: str,
    *,
    allow_existing: bool = True,
) -> Path:
    """Download and verify a Modrinth file."""

    destination = Path(destination)
    if allow_existing and verify_file_hashes(destination, file.hashes):
        return destination
    if not file.url.startswith("https://"):
        raise ValueError(f"refusing non-HTTPS download URL: {file.url}")
    await asyncio.to_thread(_download, file.url, destination, user_agent)
    if not verify_file_hashes(destination, file.hashes):
        raise ValueError(f"downloaded file failed hash verification: {destination}")
    return destination

