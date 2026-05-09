from __future__ import annotations

from typing import Literal

from mythweaver.schemas.contracts import SourceFileCandidate


def evaluate_candidate_policy(
    candidate: SourceFileCandidate,
    *,
    target_export: Literal["modrinth_pack", "curseforge_manifest", "local_instance", "prism_instance"],
    autonomous: bool,
) -> SourceFileCandidate:
    updated = candidate.model_copy(deep=True)
    if updated.acquisition_status == "unsafe_source":
        return updated
    if updated.acquisition_status in {"verified_manual_required", "metadata_incomplete"} and autonomous:
        updated.acquisition_status = "download_blocked"
        updated.warnings.append("Autonomous mode blocks manual/incomplete sources unless explicitly allowed.")
        return updated
    if updated.acquisition_status == "license_blocked":
        return updated
    if target_export == "modrinth_pack" and updated.source != "modrinth":
        updated.acquisition_status = "download_blocked"
        updated.warnings.append("Modrinth .mrpack export cannot safely include this external source.")
        return updated
    if target_export == "curseforge_manifest" and updated.source not in {"curseforge"}:
        updated.acquisition_status = "download_blocked"
        updated.warnings.append("CurseForge manifest export cannot safely include this source.")
        return updated
    return updated
