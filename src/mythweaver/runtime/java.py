from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mythweaver.runtime.contracts import RuntimeIssue


@dataclass(frozen=True)
class JavaChoice:
    java_path: str | None
    major_version: int | None
    issue: RuntimeIssue | None = None


def detect_java_candidates() -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    java_home = os.getenv("JAVA_HOME")
    if java_home:
        candidates.append(str(Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")))
    found = shutil.which("java")
    if found:
        candidates.append(found)
    if os.name == "nt":
        for root in (Path("C:/Program Files/Java"), Path("C:/Program Files/Eclipse Adoptium")):
            if root.is_dir():
                for path in root.glob("**/bin/java.exe"):
                    candidates.append(str(path))
    output = []
    for candidate in candidates:
        normalized = str(Path(candidate))
        if normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def get_java_major_version(java_path: str) -> int | None:
    try:
        completed = subprocess.run(
            [java_path, "-version"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = f"{completed.stdout}\n{completed.stderr}"
    match = re.search(r'version\s+"([^"]+)"', text)
    if not match:
        match = re.search(r"\b(?:openjdk|java)\s+([0-9][^\s]*)", text, re.IGNORECASE)
    if not match:
        return None
    version = match.group(1)
    parts = version.split(".")
    try:
        if parts[0] == "1" and len(parts) > 1:
            return int(parts[1])
        return int(parts[0])
    except ValueError:
        return None


def required_java_for_minecraft(minecraft_version: str) -> int:
    parts = _version_tuple(minecraft_version)
    if parts >= (1, 20, 5) or parts >= (1, 21, 0):
        return 21
    if parts >= (1, 18, 0):
        return 17
    if parts >= (1, 17, 0):
        return 16
    return 8


def choose_java(
    minecraft_version: str,
    explicit_java_path: str | None = None,
    *,
    major_version_probe: Callable[[str], int | None] | None = None,
) -> JavaChoice:
    major_version_probe = major_version_probe or get_java_major_version
    required = required_java_for_minecraft(minecraft_version)
    candidates = [explicit_java_path] if explicit_java_path else detect_java_candidates()
    for candidate in [item for item in candidates if item]:
        major = major_version_probe(candidate)
        if major is None:
            continue
        if major >= required:
            return JavaChoice(java_path=candidate, major_version=major)
    return JavaChoice(
        java_path=None,
        major_version=None,
        issue=RuntimeIssue(
            kind="java_version_mismatch",
            severity="fatal",
            confidence=0.95,
            message=f"Java {required}+ is required for Minecraft {minecraft_version}, but no compatible Java runtime was found.",
            evidence=[f"required_java={required}", f"candidates_checked={len([item for item in candidates if item])}"],
        ),
    )


def _version_tuple(version: str) -> tuple[int, int, int]:
    pieces = []
    for raw in version.split(".")[:3]:
        match = re.match(r"(\d+)", raw)
        pieces.append(int(match.group(1)) if match else 0)
    while len(pieces) < 3:
        pieces.append(0)
    return pieces[0], pieces[1], pieces[2]
