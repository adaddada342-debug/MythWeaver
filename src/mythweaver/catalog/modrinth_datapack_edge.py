"""Narrow Modrinth compatibility: project_type \"mod\" with datapack-only version files."""

from __future__ import annotations

from typing import Any

from mythweaver.schemas.contracts import CandidateMod

MODRINTH_MOD_LOADERS = frozenset({"fabric", "forge", "quilt", "neoforge"})

PLATFORM_MOD_DATAPACK_FILE_WARNING = (
    "Platform project_type is mod, but selected file is datapack-only; treating as manual world-creation datapack."
)


def modrinth_version_loaders_effectively_datapack_only(version: dict[str, Any]) -> bool:
    """True when the version declares datapack and no Fabric/Forge/Quilt/NeoForge loaders."""
    raw = [str(x).strip().lower() for x in version.get("loaders", []) if str(x).strip()]
    if not raw or "datapack" not in raw:
        return False
    return not any(x in MODRINTH_MOD_LOADERS for x in raw)


def modrinth_mod_project_datapack_edge_applies(*, project_type: str | None, version: dict[str, Any]) -> bool:
    if str(project_type or "mod").strip().lower() != "mod":
        return False
    return modrinth_version_loaders_effectively_datapack_only(version)


def apply_modrinth_mod_datapack_edge_to_candidate(candidate: CandidateMod, version: dict[str, Any]) -> CandidateMod:
    """Reclassify to manual datapack; preserve platform_project_type as mod; append mismatch note."""
    if not modrinth_mod_project_datapack_edge_applies(project_type=candidate.platform_project_type, version=version):
        return candidate
    why = list(candidate.why_selected)
    if PLATFORM_MOD_DATAPACK_FILE_WARNING not in why:
        why.append(PLATFORM_MOD_DATAPACK_FILE_WARNING)
    return candidate.model_copy(
        update={
            "content_kind": "datapack",
            "content_placement": "manual_world_creation",
            "why_selected": why,
        }
    )


def modrinth_version_dict_installable(
    version: dict[str, Any],
    loader: str,
    minecraft_version: str,
    *,
    require_loader: bool = True,
    relax_mod_datapack_edge: bool = False,
) -> bool:
    """Whether a Modrinth API version dict is installable for loader + Minecraft version."""
    if require_loader:
        skip_loader = relax_mod_datapack_edge and modrinth_version_loaders_effectively_datapack_only(version)
        if not skip_loader:
            loaders = [value.lower() for value in version.get("loaders", [])]
            if loader.lower() not in loaders:
                return False
    if minecraft_version != "auto":
        game_versions = [value.lower() for value in version.get("game_versions", [])]
        if minecraft_version.lower() not in game_versions:
            return False
    if version.get("status", "listed") not in {"listed", "unlisted"}:
        return False
    if not version.get("files"):
        return False
    return True


def first_installable_modrinth_version_dict(
    hit: dict[str, Any],
    versions: list[dict[str, Any]],
    *,
    loader: str,
    minecraft_version: str,
    require_loader_match: bool,
) -> dict[str, Any] | None:
    """Prefer strict loader match on mod projects before Modrinth mod/datapack-file edge relax pass."""
    relax_iters = [False]
    if require_loader_match and str(hit.get("project_type", "")).strip().lower() == "mod":
        relax_iters.append(True)
    for relax_mod_datapack_edge in relax_iters:
        for version in versions:
            if modrinth_version_dict_installable(
                version,
                loader,
                minecraft_version,
                require_loader=require_loader_match,
                relax_mod_datapack_edge=relax_mod_datapack_edge,
            ):
                return version
    return None
