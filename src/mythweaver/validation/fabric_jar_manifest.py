"""Read fabric.mod.json from the root of a Fabric mod JAR."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


def read_root_fabric_mod_json(jar_path: Path) -> dict[str, Any] | None:
    """Return parsed fabric.mod.json from jar root, or None if missing/unreadable."""
    try:
        with zipfile.ZipFile(jar_path, "r") as zf:
            names = set(zf.namelist())
            if "fabric.mod.json" not in names:
                return None
            raw = zf.read("fabric.mod.json")
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError):
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def extract_manifest_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a subset of fields for validation and reporting."""
    depends = data.get("depends") or {}
    if not isinstance(depends, dict):
        depends = {}
    breaks = data.get("breaks") or {}
    if not isinstance(breaks, dict):
        breaks = {}
    conflicts = data.get("conflicts") or {}
    if not isinstance(conflicts, dict):
        conflicts = {}
    return {
        "mod_id": data.get("id"),
        "version": data.get("version"),
        "name": data.get("name"),
        "environment": data.get("environment"),
        "depends": depends,
        "depends_minecraft": depends.get("minecraft"),
        "depends_fabricloader": depends.get("fabricloader") or depends.get("fabric-loader"),
        "depends_fabric_api": depends.get("fabric") or depends.get("fabric-api"),
        "breaks": breaks,
        "conflicts": conflicts,
    }
