from __future__ import annotations

import json
import re
from pathlib import Path

from mythweaver.schemas.contracts import BuildArtifact, RequirementProfile

SLUG_RE = re.compile(r"[^a-z0-9_]+")


def _slug(value: str) -> str:
    slug = SLUG_RE.sub("_", value.lower()).strip("_")
    return slug or "mythweaver_pack"


def _pack_format_for_version(minecraft_version: str) -> int:
    if minecraft_version in {"1.20", "1.20.1"}:
        return 15
    if minecraft_version in {"1.20.2"}:
        return 18
    if minecraft_version in {"1.20.3", "1.20.4"}:
        return 26
    return 15


def generate_lore_datapack(profile: RequirementProfile, output_dir: Path) -> BuildArtifact:
    """Generate a tiny validated datapack with startup/lore text hooks."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    namespace = "mythweaver"
    pack_meta = {
        "pack": {
            "pack_format": _pack_format_for_version(profile.minecraft_version),
            "description": f"MythWeaver generated lore hooks for {profile.name}.",
        }
    }
    (root / "pack.mcmeta").write_text(json.dumps(pack_meta, indent=2), encoding="utf-8")

    function_dir = root / "data" / namespace / "functions"
    function_dir.mkdir(parents=True, exist_ok=True)
    themes = ", ".join(profile.themes[:4]) or "adventure"
    mood = ", ".join(profile.mood[:4]) or "mystery"
    messages = [
        {"text": profile.name, "color": "aqua", "bold": True},
        {"text": f"Themes: {themes}", "color": "gray"},
        {"text": f"Mood: {mood}", "color": "dark_gray"},
    ]
    intro = [f"tellraw @a {json.dumps(message, separators=(',', ':'))}" for message in messages]
    (function_dir / "intro.mcfunction").write_text("\n".join(intro) + "\n", encoding="utf-8")

    tags_dir = root / "data" / "minecraft" / "tags" / "functions"
    tags_dir.mkdir(parents=True, exist_ok=True)
    (tags_dir / "load.json").write_text(
        json.dumps({"values": [f"{namespace}:intro"]}, indent=2),
        encoding="utf-8",
    )

    return BuildArtifact(
        kind="datapack",
        path=str(root),
        metadata={"slug": _slug(profile.name), "pack_format": pack_meta["pack"]["pack_format"]},
    )
