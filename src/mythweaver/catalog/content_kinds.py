"""Map platform project metadata to MythWeaver ContentKind values."""

from __future__ import annotations

from typing import Literal

ContentKind = Literal["mod", "datapack", "resourcepack", "shaderpack", "modpack"]
ContentPlacement = Literal["manual_world_creation", "bundle", "mods_folder", "mrpack_overrides"]

# CurseForge Minecraft (gameId 432) main classes — conservative; unknown IDs fall back to None.
_CURSEFORGE_CLASS_TO_KIND: dict[int, ContentKind] = {
    6: "mod",
    12: "resourcepack",
    # Data packs and similar world content often use dedicated classes; extend as verified.
    6945: "datapack",
    6946: "datapack",
    6552: "shaderpack",
}


def content_kind_from_modrinth_project_type(project_type: str | None) -> tuple[ContentKind, str | None]:
    """Return (internal kind, raw platform type string for debugging)."""
    raw = (project_type or "mod").strip().lower() or "mod"
    if raw == "mod":
        return "mod", raw
    if raw == "modpack":
        return "modpack", raw
    if raw == "resourcepack":
        return "resourcepack", raw
    if raw in {"shader", "shaderpack"}:
        return "shaderpack", raw
    if raw == "datapack":
        return "datapack", raw
    return "mod", raw


def content_kind_from_curseforge_class_id(class_id: int | None) -> ContentKind | None:
    if class_id is None:
        return None
    return _CURSEFORGE_CLASS_TO_KIND.get(int(class_id))


def default_placement_for_kind(kind: ContentKind) -> ContentPlacement | None:
    if kind == "datapack":
        return "manual_world_creation"
    return "bundle"


def modrinth_version_uses_loader_filter(kind: ContentKind) -> bool:
    """Fabric/Quilt loader facets apply to mods; datapacks/RP/shaders often omit loader filters."""
    return kind == "mod"
