from __future__ import annotations

from typing import Any, cast

from mythweaver.schemas.contracts import RejectedMod, SelectedModList, SourceDependencyRecord, SourceFileCandidate, SourceResolveReport
from mythweaver.sources.base import SourceProvider
from mythweaver.sources.curseforge import CurseForgeSourceProvider
from mythweaver.sources.direct_url import DirectUrlSourceProvider
from mythweaver.sources.github import GitHubReleaseSourceProvider
from mythweaver.sources.local import LocalFileSourceProvider
from mythweaver.sources.modrinth import ModrinthSourceProvider
from mythweaver.sources.planetminecraft import PlanetMinecraftSourceProvider
from mythweaver.sources.policy import ExportTarget, evaluate_candidate_policy


def provider_for_source(source: str, *, modrinth: Any = None, curseforge_api_key: str | None = None) -> SourceProvider:
    normalized = source.strip().lower()
    if normalized in {"auto", "modrinth"}:
        return cast(SourceProvider, ModrinthSourceProvider(modrinth))
    if normalized == "curseforge":
        return cast(SourceProvider, CurseForgeSourceProvider(api_key=curseforge_api_key))
    if normalized == "planetminecraft":
        return cast(SourceProvider, PlanetMinecraftSourceProvider())
    if normalized == "local":
        return cast(SourceProvider, LocalFileSourceProvider())
    if normalized == "direct_url":
        return cast(SourceProvider, DirectUrlSourceProvider())
    if normalized == "github":
        return cast(SourceProvider, GitHubReleaseSourceProvider())
    raise ValueError(f"unknown source: {source}")


async def resolve_sources_for_selected_mods(
    selected: SelectedModList,
    *,
    minecraft_version: str,
    loader: str,
    sources: list[str],
    target_export: str,
    autonomous: bool,
    modrinth: Any = None,
    curseforge_api_key: str | None = None,
    allow_manual_sources: bool = False,
) -> SourceResolveReport:
    selected_files: list[SourceFileCandidate] = []
    manifest_files: list[SourceFileCandidate] = []
    manual_required: list[SourceFileCandidate] = []
    blocked: list[SourceFileCandidate] = []
    unresolved_required_dependencies: list[RejectedMod] = []
    manually_required_dependencies: list[SourceFileCandidate] = []
    optional_dependencies: list[SourceDependencyRecord] = []
    incompatible_dependencies: list[SourceDependencyRecord] = []
    warnings: list[str] = []
    source_order = sources or ["modrinth"]
    resolved_keys: set[tuple[str, str]] = set()
    queued_dependencies: list[tuple[SourceDependencyRecord, str]] = []

    for entry in selected.mods:
        requested_source = entry.source if entry.source != "auto" else "auto"
        candidate = await _resolve_candidate(
            entry.source_ref or entry.identifier(),
            requested_source=requested_source,
            source_order=source_order,
            minecraft_version=minecraft_version,
            loader=loader,
            target_export=target_export,
            autonomous=autonomous,
            modrinth=modrinth,
            curseforge_api_key=curseforge_api_key,
            allow_manual_sources=allow_manual_sources,
            warnings=warnings,
        )
        if not candidate:
            blocked.append(
                SourceFileCandidate(
                    source="unknown",
                    slug=entry.slug,
                    project_id=entry.modrinth_id,
                    name=entry.identifier(),
                    acquisition_status="unsupported",
                    warnings=["No source provider could resolve this selected mod."],
                )
            )
            continue
        if _is_manifest_candidate(candidate, target_export):
            if _candidate_key(candidate) not in resolved_keys:
                manifest_files.append(candidate)
                resolved_keys.add(_candidate_key(candidate))
                queued_dependencies.extend((dep, candidate.project_id or candidate.slug or candidate.name) for dep in candidate.dependency_records)
        elif candidate.acquisition_status == "verified_auto":
            if _candidate_key(candidate) not in resolved_keys:
                selected_files.append(candidate)
                resolved_keys.add(_candidate_key(candidate))
                queued_dependencies.extend((dep, candidate.project_id or candidate.slug or candidate.name) for dep in candidate.dependency_records)
        elif candidate.acquisition_status == "verified_manual_required" and allow_manual_sources:
            manual_required.append(candidate)
        elif candidate.acquisition_status in {"verified_manual_required", "metadata_incomplete"}:
            manual_required.append(candidate)
        else:
            blocked.append(candidate)

    while queued_dependencies:
        dependency, required_by = queued_dependencies.pop(0)
        dependency.required_by = required_by
        if dependency.dependency_type == "optional":
            optional_dependencies.append(dependency)
            continue
        if dependency.dependency_type in {"incompatible", "embedded"}:
            incompatible_dependencies.append(dependency)
            continue
        if dependency.dependency_type != "required":
            continue
        if not dependency.project_id:
            unresolved_required_dependencies.append(
                RejectedMod(
                    project_id=dependency.file_name or dependency.version_id or "unknown",
                    reason="unresolved_required_dependency",
                    detail=f"Required by {required_by}; dependency metadata did not include a project id.",
                )
            )
            continue
        if _dependency_already_resolved(dependency, resolved_keys):
            continue
        dependency_source_order = _dependency_source_order(dependency, source_order)
        if dependency.source not in {"unknown", "auto"} and dependency.source not in source_order:
            manual = SourceFileCandidate(
                source=dependency.source,
                project_id=dependency.project_id,
                name=dependency.project_id,
                acquisition_status="verified_manual_required",
                warnings=[f"Required by {required_by}, but {dependency.source} is not in allowed sources."],
            )
            manual_required.append(manual)
            manually_required_dependencies.append(manual)
            continue
        candidate = await _resolve_candidate(
            dependency.project_id,
            requested_source=dependency.source if dependency.source != "unknown" else "auto",
            source_order=dependency_source_order,
            minecraft_version=minecraft_version,
            loader=loader,
            target_export=target_export,
            autonomous=autonomous,
            modrinth=modrinth,
            curseforge_api_key=curseforge_api_key,
            allow_manual_sources=allow_manual_sources,
            warnings=warnings,
        )
        if not candidate:
            unresolved_required_dependencies.append(
                RejectedMod(
                    project_id=dependency.project_id,
                    reason="unresolved_required_dependency",
                    detail=f"Required by {required_by}",
                )
            )
            continue
        if dependency.version_id and candidate.file_id and candidate.file_id != dependency.version_id:
            unresolved_required_dependencies.append(
                RejectedMod(
                    project_id=dependency.project_id,
                    title=candidate.name,
                    reason="dependency_version_mismatch",
                    detail=f"Required by {required_by}; expected file/version {dependency.version_id}, resolved {candidate.file_id}.",
                )
            )
            continue
        if _is_manifest_candidate(candidate, target_export):
            key = _candidate_key(candidate)
            if key not in resolved_keys:
                manifest_files.append(candidate)
                resolved_keys.add(key)
                queued_dependencies.extend((dep, candidate.project_id or candidate.slug or candidate.name) for dep in candidate.dependency_records)
        elif candidate.acquisition_status == "verified_auto":
            key = _candidate_key(candidate)
            if key not in resolved_keys:
                selected_files.append(candidate)
                resolved_keys.add(key)
                queued_dependencies.extend((dep, candidate.project_id or candidate.slug or candidate.name) for dep in candidate.dependency_records)
        elif candidate.acquisition_status in {"verified_manual_required", "metadata_incomplete"}:
            manual_required.append(candidate)
            manually_required_dependencies.append(candidate)
        else:
            unresolved_required_dependencies.append(
                RejectedMod(
                    project_id=dependency.project_id,
                    title=candidate.name,
                    reason="required_dependency_not_acquirable",
                    detail=f"Required by {required_by}; {candidate.source} returned {candidate.acquisition_status}.",
                )
            )

    installable_files = selected_files + manifest_files
    transitive_dependency_count = max(0, len(installable_files) - len(selected.mods))
    source_breakdown: dict[str, int] = {}
    for candidate in installable_files:
        source_breakdown[candidate.source] = source_breakdown.get(candidate.source, 0) + 1
    export_blockers = _export_blockers(
        target_export=target_export,
        selected_files=selected_files,
        manifest_files=manifest_files,
        manual_required=manual_required,
        blocked=blocked,
        unresolved_required_dependencies=unresolved_required_dependencies,
    )
    closure_passed = not unresolved_required_dependencies and not blocked and not manual_required
    export_supported = not export_blockers and bool(installable_files)
    status = "resolved" if installable_files and closure_passed and export_supported else ("partial" if installable_files or manual_required else "failed")
    return SourceResolveReport(
        status=cast(Any, status),
        minecraft_version=minecraft_version,
        loader=loader,
        selected_files=selected_files,
        manifest_files=manifest_files,
        manual_required=manual_required,
        blocked=blocked,
        warnings=warnings,
        required_count=len(selected.mods),
        missing_count=len(unresolved_required_dependencies),
        unsupported_count=len(blocked),
        manual_required_count=len(manual_required) + len(manually_required_dependencies),
        export_supported=export_supported,
        export_blockers=export_blockers,
        unresolved_required_dependencies=unresolved_required_dependencies,
        manually_required_dependencies=manually_required_dependencies,
        optional_dependencies=optional_dependencies,
        incompatible_dependencies=incompatible_dependencies,
        transitive_dependency_count=transitive_dependency_count,
        dependency_source_breakdown=source_breakdown,
        dependency_closure_passed=closure_passed,
    )


async def _resolve_candidate(
    ref: str,
    *,
    requested_source: str,
    source_order: list[str],
    minecraft_version: str,
    loader: str,
    target_export: str,
    autonomous: bool,
    modrinth: Any,
    curseforge_api_key: str | None,
    allow_manual_sources: bool,
    warnings: list[str],
) -> SourceFileCandidate | None:
    provider_names = source_order if requested_source == "auto" else [requested_source]
    for provider_name in provider_names:
        provider = provider_for_source(provider_name, modrinth=modrinth, curseforge_api_key=curseforge_api_key)
        if not provider.is_configured():
            if provider.source_name == "curseforge":
                warnings.append("CURSEFORGE_API_KEY is not configured; CurseForge dependencies require setup before they can be acquired.")
            else:
                warnings.append(f"{provider.source_name} provider is not configured.")
            continue
        candidate = await provider.resolve_file(ref, minecraft_version=minecraft_version, loader=loader)
        if candidate:
            return evaluate_candidate_policy(
                candidate,
                target_export=cast(ExportTarget, target_export),
                autonomous=autonomous and not allow_manual_sources,
            )
    return None


def _candidate_key(candidate: SourceFileCandidate) -> tuple[str, str]:
    return candidate.source, candidate.project_id or candidate.slug or candidate.file_id or candidate.name


def _dependency_already_resolved(dependency: SourceDependencyRecord, resolved_keys: set[tuple[str, str]]) -> bool:
    if not dependency.project_id:
        return False
    return (dependency.source, dependency.project_id) in resolved_keys


def _dependency_source_order(dependency: SourceDependencyRecord, source_order: list[str]) -> list[str]:
    if dependency.source in source_order:
        return [dependency.source, *[source for source in source_order if source != dependency.source]]
    return source_order


def _is_manifest_candidate(candidate: SourceFileCandidate, target_export: str) -> bool:
    return (
        target_export == "curseforge_manifest"
        and candidate.source == "curseforge"
        and bool(candidate.project_id)
        and bool(candidate.file_id)
        and candidate.acquisition_status in {"verified_auto", "verified_manual_required"}
    )


def _export_blockers(
    *,
    target_export: str,
    selected_files: list[SourceFileCandidate],
    manifest_files: list[SourceFileCandidate],
    manual_required: list[SourceFileCandidate],
    blocked: list[SourceFileCandidate],
    unresolved_required_dependencies: list[RejectedMod],
) -> list[str]:
    blockers: list[str] = []
    if blocked:
        blockers.append(f"{len(blocked)} file(s) blocked by source/export policy.")
    if unresolved_required_dependencies:
        blockers.append(f"{len(unresolved_required_dependencies)} required dependency/dependencies unresolved.")
    if target_export == "curseforge_manifest":
        if selected_files:
            blockers.append("CurseForge manifest export cannot include non-manifest files.")
        if manual_required:
            blockers.append("Manual files are not CurseForge manifest-eligible.")
    elif manual_required:
        blockers.append(f"{len(manual_required)} file(s) require manual acquisition.")
    return blockers
