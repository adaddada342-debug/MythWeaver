from __future__ import annotations

from typing import Literal

from mythweaver.schemas.contracts import SourceFileCandidate

ExportTarget = Literal[
    "modrinth_pack",
    "curseforge_manifest",
    "prism_instance",
    "local_instance",
    "multimc_instance",
]


def evaluate_candidate_policy(
    candidate: SourceFileCandidate,
    *,
    target_export: ExportTarget,
    autonomous: bool,
) -> SourceFileCandidate:
    updated = candidate.model_copy(deep=True)
    if updated.acquisition_status == "unsafe_source":
        return updated
    if updated.acquisition_status == "license_blocked":
        return updated
    if target_export == "modrinth_pack" and updated.source != "modrinth":
        updated.acquisition_status = "download_blocked"
        updated.warnings.append("Modrinth .mrpack export cannot safely include this external source.")
        return updated
    if target_export == "modrinth_pack" and not _has_download_and_hashes(updated):
        updated.acquisition_status = "metadata_incomplete"
        updated.warnings.append("Modrinth .mrpack export requires download URLs and hashes.")
        return updated
    if target_export == "curseforge_manifest":
        if updated.source != "curseforge":
            updated.acquisition_status = "download_blocked"
            updated.warnings.append("CurseForge manifest export cannot safely include this source.")
            return updated
        if not updated.project_id or not updated.file_id:
            updated.acquisition_status = "metadata_incomplete"
            updated.warnings.append("CurseForge manifest export requires projectID and fileID.")
            return updated
        if updated.acquisition_status == "metadata_incomplete":
            updated.acquisition_status = "verified_manual_required"
        return updated
    if updated.source == "direct_url" and autonomous:
        updated.acquisition_status = "download_blocked"
        updated.warnings.append("Direct URL sources are blocked in autonomous mode without explicit allow flags and strong hashes.")
        return updated
    if target_export in {"local_instance", "prism_instance", "multimc_instance"}:
        if updated.source in {"github", "planetminecraft"} and updated.acquisition_status != "verified_auto":
            updated.acquisition_status = "verified_manual_required"
            updated.warnings.append(f"{updated.source} requires manual review unless release asset metadata proves compatibility and hashes.")
        if updated.acquisition_status == "verified_auto" and not _has_download_and_hashes(updated):
            updated.acquisition_status = "metadata_incomplete"
            updated.warnings.append("Local/Prism export requires a download URL or local path plus hashes.")
            return updated
    if updated.acquisition_status in {"verified_manual_required", "metadata_incomplete"} and autonomous:
        updated.acquisition_status = "download_blocked"
        updated.warnings.append("Autonomous mode blocks manual/incomplete sources unless explicitly allowed.")
        return updated
    return updated


def _has_download_and_hashes(candidate: SourceFileCandidate) -> bool:
    return bool(candidate.download_url and candidate.hashes)
