from __future__ import annotations

from mythweaver.schemas.contracts import RejectedMod, SelectedModList, SourceDependencyRecord, SourceFileCandidate, SourceResolveReport
from mythweaver.sources.curseforge import CurseForgeSourceProvider
from mythweaver.sources.direct_url import DirectUrlSourceProvider
from mythweaver.sources.github import GitHubReleaseSourceProvider
from mythweaver.sources.local import LocalFileSourceProvider
from mythweaver.sources.modrinth import ModrinthSourceProvider
from mythweaver.sources.planetminecraft import PlanetMinecraftSourceProvider
from mythweaver.sources.policy import evaluate_candidate_policy


def provider_for_source(source: str, *, modrinth=None, curseforge_api_key: str | None = None):
    normalized = source.strip().lower()
    if normalized in {"auto", "modrinth"}:
        return ModrinthSourceProvider(modrinth)
    if normalized == "curseforge":
        return CurseForgeSourceProvider(api_key=curseforge_api_key)
    if normalized == "planetminecraft":
        return PlanetMinecraftSourceProvider()
    if normalized == "local":
        return LocalFileSourceProvider()
    if normalized == "direct_url":
        return DirectUrlSourceProvider()
    if normalized == "github":
        return GitHubReleaseSourceProvider()
    raise ValueError(f"unknown source: {source}")


async def resolve_sources_for_selected_mods(
    selected: SelectedModList,
    *,
    minecraft_version: str,
    loader: str,
    sources: list[str],
    target_export: str,
    autonomous: bool,
    modrinth=None,
    curseforge_api_key: str | None = None,
    allow_manual_sources: bool = False,
) -> SourceResolveReport:
    selected_files: list[SourceFileCandidate] = []
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
        if candidate.acquisition_status == "verified_auto":
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
        if candidate.acquisition_status == "verified_auto":
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

    transitive_dependency_count = max(0, len(selected_files) - len(selected.mods))
    source_breakdown: dict[str, int] = {}
    for candidate in selected_files:
        source_breakdown[candidate.source] = source_breakdown.get(candidate.source, 0) + 1
    closure_passed = not unresolved_required_dependencies and not manually_required_dependencies and not blocked and not manual_required
    status = "resolved" if selected_files and closure_passed else ("partial" if selected_files or manual_required else "failed")
    return SourceResolveReport(
        status=status,
        minecraft_version=minecraft_version,
        loader=loader,
        selected_files=selected_files,
        manual_required=manual_required,
        blocked=blocked,
        warnings=warnings,
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
    modrinth,
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
                target_export=target_export,
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
