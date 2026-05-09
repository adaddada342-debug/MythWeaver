from __future__ import annotations

from collections import deque

from mythweaver.schemas.contracts import (
    CandidateMod,
    DependencyEdge,
    RejectedMod,
    RequirementProfile,
    ResolvedPack,
)


def _candidate_map(candidates: list[CandidateMod]) -> dict[str, CandidateMod]:
    return {candidate.project_id: candidate for candidate in candidates}


def resolve_pack(
    requested_project_ids: list[str],
    candidates: list[CandidateMod],
    profile: RequirementProfile,
    loader_version: str | None = None,
) -> ResolvedPack:
    """Resolve requested projects plus required dependencies from the candidate pool."""

    by_id = _candidate_map(candidates)
    selected: dict[str, CandidateMod] = {}
    rejected: list[RejectedMod] = []
    edges: list[DependencyEdge] = []
    queue: deque[str] = deque(requested_project_ids)

    while queue:
        project_id = queue.popleft()
        if project_id in selected:
            continue
        candidate = by_id.get(project_id)
        if not candidate:
            rejected.append(
                RejectedMod(project_id=project_id, reason="requested_project_not_found")
            )
            continue
        if candidate.score.hard_reject_reason:
            rejected.append(
                RejectedMod(
                    project_id=project_id,
                    title=candidate.title,
                    reason=candidate.score.hard_reject_reason,
                )
            )
            continue

        selected[project_id] = candidate
        for dependency in candidate.selected_version.dependencies:
            if dependency.dependency_type == "required" and dependency.project_id:
                edges.append(
                    DependencyEdge(
                        source_project_id=project_id,
                        target_project_id=dependency.project_id,
                        dependency_type="required",
                    )
                )
                if dependency.project_id not in by_id:
                    rejected.append(
                        RejectedMod(
                            project_id=dependency.project_id,
                            reason="missing_required_dependency",
                            detail=f"Required by {candidate.project_id}",
                        )
                    )
                elif dependency.project_id not in selected:
                    queue.append(dependency.project_id)
            elif dependency.dependency_type == "incompatible" and dependency.project_id:
                if dependency.project_id in requested_project_ids:
                    rejected.append(
                        RejectedMod(
                            project_id=dependency.project_id,
                            reason="incompatible_dependency",
                            detail=f"Incompatible with {candidate.project_id}",
                        )
                    )

    return ResolvedPack(
        name=profile.name,
        minecraft_version=profile.minecraft_version,
        loader=profile.loader,
        loader_version=loader_version,
        selected_mods=list(selected.values()),
        rejected_mods=rejected,
        dependency_edges=edges,
    )

