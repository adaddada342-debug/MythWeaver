from __future__ import annotations

from typing import Any, cast

from mythweaver.catalog.loaders import normalize_loader
from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport, TargetCandidate, TargetMatrixReport
from mythweaver.sources.resolver import resolve_sources_for_selected_mods

DEFAULT_LOADERS = ["fabric", "forge", "neoforge", "quilt"]


async def build_target_matrix(
    selected: SelectedModList,
    *,
    sources: list[str],
    candidate_versions: list[str] | None = None,
    candidate_loaders: list[str] | None = None,
    target_export: str,
    facade: Any | None = None,
    modrinth: Any | None = None,
    curseforge_api_key: str | None = None,
    allow_manual_sources: bool = False,
) -> TargetMatrixReport:
    requested_version = selected.minecraft_version
    requested_loader = normalize_loader(selected.loader)
    active_modrinth = modrinth or getattr(facade, "modrinth", None)
    versions = await _candidate_versions(selected, candidate_versions, active_modrinth)
    loaders = _candidate_loaders(requested_loader, candidate_loaders)
    if requested_version not in {"auto", "any"}:
        versions = [requested_version]
    if requested_loader not in {"auto", "any"}:
        loaders = [requested_loader]

    candidates: list[TargetCandidate] = []
    for version in versions:
        for loader in loaders:
            report = await resolve_sources_for_selected_mods(
                selected,
                minecraft_version=version,
                loader=loader,
                sources=sources,
                target_export=target_export,
                autonomous=not allow_manual_sources,
                modrinth=active_modrinth,
                curseforge_api_key=curseforge_api_key,
                allow_manual_sources=allow_manual_sources,
            )
            selected_count = len(report.selected_files) + len(report.manifest_files)
            required_count = report.required_count or len(selected.mods)
            missing_count = report.missing_count or len(report.unresolved_required_dependencies)
            unsupported_count = report.unsupported_count or len(report.blocked)
            manual_required_count = report.manual_required_count or len(report.manual_required) + len(report.manually_required_dependencies)
            score = _score_candidate(
                selected_count=selected_count,
                required_count=required_count,
                missing_count=missing_count,
                unsupported_count=unsupported_count,
                manual_required_count=manual_required_count,
                dependency_closure_passed=report.dependency_closure_passed,
                export_supported=report.export_supported,
                minecraft_version=version,
            )
            candidates.append(
                TargetCandidate(
                    minecraft_version=version,
                    loader=loader,
                    sources=sources,
                    selected_count=selected_count,
                    required_count=required_count,
                    missing_count=missing_count,
                    unsupported_count=unsupported_count,
                    manual_required_count=manual_required_count,
                    score=score,
                    reasons=_candidate_reasons(report),
                    warnings=report.warnings + report.export_blockers,
                )
            )

    best = max(candidates, key=lambda candidate: candidate.score, default=None)
    status = "failed"
    if best and best.selected_count and best.missing_count == 0 and best.unsupported_count == 0:
        status = "resolved" if best.manual_required_count == 0 else "partial"
    elif best and best.selected_count:
        status = "partial"
    report_warnings: list[str] = []
    if not candidates:
        report_warnings.append("No target candidates were evaluated.")
    elif status == "failed":
        report_warnings.append("No target candidate produced exportable required coverage.")
    return TargetMatrixReport(
        requested_minecraft_version=requested_version,
        requested_loader=selected.loader,
        considered_versions=versions,
        considered_loaders=loaders,
        best=best,
        candidates=sorted(candidates, key=lambda candidate: candidate.score, reverse=True),
        status=cast(Any, status),
        warnings=report_warnings,
    )


async def _candidate_versions(selected: SelectedModList, explicit: list[str] | None, modrinth: Any | None) -> list[str]:
    if explicit:
        return [item.strip() for item in explicit if item and item.strip()]
    versions = [
        version
        for entry in selected.mods
        for version in [entry.source_file_id or ""]
        if version.startswith("1.")
    ]
    if versions:
        return list(dict.fromkeys(versions))
    if modrinth is None or not hasattr(modrinth, "get_game_versions"):
        return []
    try:
        tags = await modrinth.get_game_versions()
    except Exception:
        return []
    stable = [
        str(item.get("version"))
        for item in tags
        if item.get("version") and item.get("version_type", "release") == "release"
    ]
    return stable[:8]


def _candidate_loaders(requested_loader: str, explicit: list[str] | None) -> list[str]:
    if explicit:
        values = [normalize_loader(item) for item in explicit]
    elif requested_loader in {"auto", "any"}:
        values = DEFAULT_LOADERS
    else:
        values = [requested_loader]
    return [item for item in dict.fromkeys(values) if item not in {"unknown", "vanilla", "auto", "any"}]


def _score_candidate(
    *,
    selected_count: int,
    required_count: int,
    missing_count: int,
    unsupported_count: int,
    manual_required_count: int,
    dependency_closure_passed: bool,
    export_supported: bool,
    minecraft_version: str,
) -> float:
    coverage = selected_count / max(required_count, 1)
    score = coverage * 100
    score -= missing_count * 30
    score -= unsupported_count * 25
    score -= manual_required_count * 10
    if dependency_closure_passed:
        score += 15
    if export_supported:
        score += 10
    score += _modern_version_bonus(minecraft_version)
    return round(score, 3)


def _modern_version_bonus(version: str) -> float:
    parts = version.split(".")
    try:
        major_minor = tuple(int(part) for part in parts[:2])
        patch = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        return 0.0
    return major_minor[1] + patch / 100


def _candidate_reasons(report: SourceResolveReport) -> list[str]:
    reasons = [
        f"selected={len(report.selected_files) + len(report.manifest_files)}",
        f"manual_required={len(report.manual_required) + len(report.manually_required_dependencies)}",
        f"blocked={len(report.blocked)}",
    ]
    if report.dependency_closure_passed:
        reasons.append("dependency_closure_passed")
    if report.export_supported:
        reasons.append("export_supported")
    return reasons
