from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from mythweaver.catalog.version_policy import select_minecraft_version
from mythweaver.modrinth.client import candidate_from_project_hit
from mythweaver.schemas.contracts import CandidateMod, RejectedMod, SearchStrategy


@dataclass
class DiscoveryResult:
    candidates: list[CandidateMod] = field(default_factory=list)
    rejected: list[RejectedMod] = field(default_factory=list)
    minecraft_version: str = "auto"
    hits: list[dict[str, Any]] = field(default_factory=list)


def _project_id(hit: dict[str, Any]) -> str:
    return hit.get("project_id") or hit.get("id") or hit.get("slug") or ""


def _installable(version: dict[str, Any], loader: str, minecraft_version: str) -> str | None:
    if loader not in [value.lower() for value in version.get("loaders", [])]:
        return "loader_mismatch"
    if minecraft_version != "auto":
        versions = [value.lower() for value in version.get("game_versions", [])]
        if minecraft_version.lower() not in versions:
            return "minecraft_version_mismatch"
    if version.get("status", "listed") not in {"listed", "unlisted"}:
        return "version_status_not_installable"
    if not version.get("files"):
        return "missing_download_file"
    return None


def _first_candidate(
    hit: dict[str, Any],
    versions: list[dict[str, Any]],
    *,
    loader: str,
    minecraft_version: str,
) -> tuple[CandidateMod | None, RejectedMod | None]:
    project_id = _project_id(hit)
    for version in versions:
        reason = _installable(version, loader, minecraft_version)
        if reason:
            continue
        try:
            return candidate_from_project_hit(hit, version), None
        except (KeyError, ValueError, ValidationError) as exc:
            return None, RejectedMod(project_id=project_id, reason="invalid_modrinth_metadata", detail=str(exc))
    return None, RejectedMod(project_id=project_id, reason="no_installable_version")


async def _search_hits(modrinth: object, strategy: SearchStrategy) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for plan in strategy.search_plans:
        response = await modrinth.search_projects(plan)
        for hit in response.get("hits", []):
            project_id = _project_id(hit)
            if project_id and project_id not in by_id:
                by_id[project_id] = hit
    return list(by_id.values())


async def discover_candidates(modrinth: object, strategy: SearchStrategy) -> DiscoveryResult:
    profile = strategy.profile
    hits = await _search_hits(modrinth, strategy)
    preliminary: list[CandidateMod] = []
    rejected: list[RejectedMod] = []

    for hit in hits:
        project_id = _project_id(hit)
        versions = await modrinth.list_project_versions(
            project_id,
            loader=profile.loader,
            minecraft_version=profile.minecraft_version,
            include_changelog=False,
        )
        candidate, rejection = _first_candidate(
            hit,
            versions,
            loader=profile.loader,
            minecraft_version=profile.minecraft_version,
        )
        if candidate:
            preliminary.append(candidate)
        elif rejection:
            rejected.append(rejection)

    if not preliminary:
        return DiscoveryResult(rejected=rejected, minecraft_version=profile.minecraft_version, hits=hits)

    minecraft_version = profile.minecraft_version
    if minecraft_version == "auto":
        minecraft_version = select_minecraft_version(preliminary).version

    verified: list[CandidateMod] = []
    for hit in hits:
        project_id = _project_id(hit)
        versions = await modrinth.list_project_versions(
            project_id,
            loader=profile.loader,
            minecraft_version=minecraft_version,
            include_changelog=False,
        )
        candidate, rejection = _first_candidate(
            hit,
            versions,
            loader=profile.loader,
            minecraft_version=minecraft_version,
        )
        if candidate:
            verified.append(candidate)
        elif rejection:
            rejected.append(rejection)

    return DiscoveryResult(
        candidates=verified,
        rejected=rejected,
        minecraft_version=minecraft_version,
        hits=hits,
    )

