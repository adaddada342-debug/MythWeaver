from __future__ import annotations

from pydantic import ValidationError

from mythweaver.modrinth.client import candidate_from_project_hit
from mythweaver.schemas.contracts import CandidateMod, RejectedMod, RequirementProfile


async def expand_required_dependencies(
    modrinth: object,
    candidates: list[CandidateMod],
    profile: RequirementProfile,
    minecraft_version: str,
) -> tuple[list[CandidateMod], list[RejectedMod]]:
    by_id = {candidate.project_id: candidate for candidate in candidates}
    rejected: list[RejectedMod] = []
    queue = list(candidates)

    while queue:
        candidate = queue.pop(0)
        if getattr(candidate, "content_kind", "mod") != "mod":
            continue
        for dependency in candidate.selected_version.dependencies:
            if dependency.dependency_type != "required" or not dependency.project_id:
                continue
            if dependency.project_id in by_id:
                continue
            versions = await modrinth.list_project_versions(
                dependency.project_id,
                loader=profile.loader,
                minecraft_version=minecraft_version,
                include_changelog=False,
            )
            try:
                hit = await modrinth.get_project(dependency.project_id)
            except (AttributeError, KeyError, TypeError, ValueError):
                hit = None
            if not hit:
                rejected.append(
                    RejectedMod(
                        project_id=dependency.project_id,
                        reason="unresolved_dependency_metadata",
                        detail=f"Required by {candidate.project_id}",
                    )
                )
                continue
            hit.setdefault("project_id", hit.get("id", dependency.project_id))
            hit.setdefault("versions", [minecraft_version])
            added = None
            for version in versions:
                try:
                    added = candidate_from_project_hit(hit, version)
                    added.selection_type = "dependency_added"
                    break
                except (KeyError, ValueError, ValidationError):
                    continue
            if added is None:
                rejected.append(
                    RejectedMod(
                        project_id=dependency.project_id,
                        reason="missing_required_dependency",
                        detail=f"Required by {candidate.project_id}",
                    )
                )
                continue
            by_id[added.project_id] = added
            queue.append(added)

    return list(by_id.values()), rejected
