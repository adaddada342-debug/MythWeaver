from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from mythweaver.schemas.contracts import CandidateMod


@dataclass(frozen=True)
class VersionChoice:
    version: str
    supporting_project_ids: list[str]
    coverage: int


def select_minecraft_version(
    candidates: list[CandidateMod],
    *,
    preferred_versions: list[str] | None = None,
) -> VersionChoice:
    """Choose the Minecraft version with the best verified candidate coverage."""

    coverage: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        for version in candidate.game_versions:
            coverage[version].append(candidate.project_id)
    if not coverage:
        raise ValueError("cannot select Minecraft version without candidate game_versions")

    preferred_order = {version: index for index, version in enumerate(preferred_versions or [])}

    def key(item: tuple[str, list[str]]) -> tuple[int, int, str]:
        version, project_ids = item
        preference = -preferred_order.get(version, 10_000)
        return (len(project_ids), preference, version)

    version, project_ids = max(coverage.items(), key=key)
    return VersionChoice(
        version=version,
        supporting_project_ids=sorted(project_ids),
        coverage=len(project_ids),
    )

