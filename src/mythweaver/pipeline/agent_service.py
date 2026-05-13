from __future__ import annotations

import json
import inspect
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mythweaver.autopilot.contracts import AutopilotReport, AutopilotRequest
from mythweaver.autopilot.loop import run_autopilot
from mythweaver.builders.curseforge_manifest import build_curseforge_manifest
from mythweaver.builders.paths import safe_slug
from mythweaver.builders.source_instance import build_source_instance
from mythweaver.catalog.modrinth_datapack_edge import (
    apply_modrinth_mod_datapack_edge_to_candidate,
    modrinth_mod_project_datapack_edge_applies,
    modrinth_version_dict_installable,
    modrinth_version_loaders_effectively_datapack_only,
)
from mythweaver.catalog.target_matrix import build_target_matrix
from mythweaver.handoff import (
    write_cloud_ai_agent_repair_prompt,
    write_cloud_ai_blueprint_selection_prompt,
    write_cloud_ai_crash_repair_prompt,
    write_cloud_ai_design_prompt,
    write_cloud_ai_design_repair_prompt,
    write_cloud_ai_fix_selected_mods_prompt,
    write_cloud_ai_repair_prompt,
    write_cloud_ai_review_prompt,
)
from mythweaver.knowledge.compatibility import CompatibilityMemory
from mythweaver.knowledge.fabric_artifact_policy import shallow_search_blocked
from mythweaver.launcher.runtime import run_launch_check, write_runtime_smoke_report
from mythweaver.launcher.setup import setup_launcher_instance, write_launcher_reports
from mythweaver.modrinth.client import candidate_from_project_hit
from mythweaver.pipeline.constraints import infer_candidate_capabilities
from mythweaver.pipeline.dependencies import expand_required_dependencies
from mythweaver.pipeline.crash_analysis import analyze_crash_report
from mythweaver.pipeline.pack_quality import (
    generate_pack_blueprint,
    infer_pack_design_from_concept,
    review_pack_design,
    review_selected_mods_against_design,
)
from mythweaver.pipeline.selection import is_novelty_candidate
from mythweaver.sources.resolver import provider_for_source, resolve_sources_for_selected_mods
from mythweaver.schemas.contracts import (
    AgentCheckFinding,
    AgentCheckReport,
    AgentPackReport,
    AutonomousBuildAttempt,
    AutonomousBuildReport,
    BuildArtifact,
    CandidateMod,
    CrashAnalysisReport,
    CrashFinding,
    DependencyImpactReport,
    LaunchValidationReport,
    LauncherInstanceReport,
    LauncherValidationReport,
    Loader,
    PackBlueprint,
    PackDesign,
    PackDesignReviewReport,
    PillarCoverage,
    RepairOption,
    RepairReport,
    RejectedMod,
    RemovedSelectedMod,
    RequirementProfile,
    ResolvedPack,
    SearchPlan,
    ReviewIssue,
    SelectedModEntry,
    SelectedModList,
    SelectedModReviewReport,
    StabilizationAttempt,
    StabilizationReport,
    RuntimeSmokeTestReport,
    SourceResolveReport,
    SourceSearchResult,
    ValidationReport,
)
from mythweaver.validation.crash_analyzer import analyze_failure


class AgentModpackService:
    """Deterministic Modrinth tooling for externally curated mod lists."""

    def __init__(self, facade: object) -> None:
        self.facade = facade
        self.settings = getattr(facade, "settings", None)
        self.memory = CompatibilityMemory(getattr(self.settings, "data_dir", Path("knowledge")))

    def design_pack_from_concept(
        self,
        concept_text: str,
        *,
        output_dir: Path | None = None,
        name: str | None = None,
        minecraft_version: str = "1.20.1",
        loader: Loader = "fabric",
        write_prompt: bool = True,
    ) -> PackDesign:
        design = infer_pack_design_from_concept(
            concept_text,
            name=name,
            minecraft_version=minecraft_version,
            loader=loader,
        )
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            design_path = output_dir / "pack_design.json"
            design_path.write_text(design.model_dump_json(indent=2), encoding="utf-8")
            if write_prompt:
                write_cloud_ai_design_prompt(design, output_dir=output_dir)
        return design

    def review_pack_design(
        self,
        design: PackDesign,
        *,
        output_dir: Path | None = None,
        write_prompt: bool = True,
    ) -> PackDesignReviewReport:
        report = review_pack_design(design)
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            report.output_dir = str(output_dir)
            if write_prompt:
                prompt = write_cloud_ai_design_repair_prompt(report, output_dir=output_dir)
                report.cloud_ai_prompt_path = str(prompt)
            _write_design_review_report(report, output_dir)
        return report

    def blueprint_pack_from_design(
        self,
        design: PackDesign,
        *,
        design_path: Path | None = None,
        output_dir: Path | None = None,
        write_prompt: bool = True,
    ) -> PackBlueprint:
        blueprint = generate_pack_blueprint(design)
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            blueprint.output_dir = str(output_dir)
            blueprint_path = output_dir / "pack_blueprint.json"
            blueprint_path.write_text(blueprint.model_dump_json(indent=2), encoding="utf-8")
            if write_prompt:
                prompt = write_cloud_ai_blueprint_selection_prompt(
                    design_path or output_dir / "pack_design.json",
                    blueprint,
                    output_dir=output_dir,
                )
                blueprint.cloud_ai_prompt_path = str(prompt)
                blueprint_path.write_text(blueprint.model_dump_json(indent=2), encoding="utf-8")
        return blueprint

    async def search_mods(
        self,
        query: str,
        *,
        loader: str = "fabric",
        minecraft_version: str = "auto",
        limit: int = 20,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        capability: list[str] | None = None,
        role: str | None = None,
        client: str | None = None,
        server: str | None = None,
        min_downloads: int = 0,
        sort: str = "relevance",
    ) -> dict[str, Any]:
        plan = SearchPlan(
            query=query,
            loader=loader,
            minecraft_version=minecraft_version,
            limit=limit,
            index=_sort_index(sort),
            client_side=client,
            server_side=server,
        )
        response = await self.facade.modrinth.search_projects(plan)
        results: list[dict[str, Any]] = []
        for hit in response.get("hits", []):
            if hit.get("downloads", 0) < min_downloads:
                continue
            text = _hit_text(hit)
            if include and not all(term.lower() in text for term in include):
                continue
            if exclude and any(term.lower() in text for term in exclude):
                continue
            inspected = await self._inspect_hit(hit, loader=loader, minecraft_version=minecraft_version)
            inspected["local_memory"] = self.memory.hints_for_mods(
                mods=[inspected["slug"], inspected["project_id"]],
                minecraft_version=minecraft_version,
                loader=loader,
            )
            if capability and not set(capability) & set(inspected["capabilities"]):
                continue
            if role and inspected["probable_role"] != role:
                continue
            lcv = inspected.get("latest_compatible_version")
            vn = ""
            if isinstance(lcv, dict):
                vn = str(lcv.get("version_number") or "")
            blocked = shallow_search_blocked(
                slug=str(inspected.get("slug") or ""),
                title=str(inspected.get("title") or inspected.get("name") or inspected.get("slug") or ""),
                version_number=vn or "1.0.0",
            )
            if blocked:
                continue
            results.append(inspected)
        return {"query": query, "loader": loader, "minecraft_version": minecraft_version, "results": results}

    async def inspect_mod(self, identifier: str, *, loader: str = "fabric", minecraft_version: str = "auto") -> dict[str, Any]:
        project = await self.facade.modrinth.get_project(identifier)
        inspected = await self._inspect_hit(project, loader=loader, minecraft_version=minecraft_version)
        inspected["local_memory"] = self.memory.hints_for_mods(
            mods=[inspected["slug"], inspected["project_id"]],
            minecraft_version=minecraft_version,
            loader=loader,
        )
        return inspected

    async def compare_mods(self, identifiers: list[str], *, loader: str = "fabric", minecraft_version: str = "auto") -> dict[str, Any]:
        candidates = []
        for identifier in identifiers:
            try:
                candidates.append(await self.inspect_mod(identifier, loader=loader, minecraft_version=minecraft_version))
            except Exception as exc:
                candidates.append(
                    {
                        "identifier": identifier,
                        "slug": identifier,
                        "installable": False,
                        "warnings": [str(exc)],
                        "capabilities": [],
                    }
                )
        return {"loader": loader, "minecraft_version": minecraft_version, "candidates": candidates}

    async def source_search(
        self,
        query: str,
        *,
        minecraft_version: str,
        loader: str,
        sources: list[str] | None = None,
        limit: int = 20,
        output_dir: Path | None = None,
    ) -> list[SourceSearchResult]:
        reports: list[SourceSearchResult] = []
        for source in sources or ["modrinth"]:
            provider = provider_for_source(
                source,
                modrinth=getattr(self.facade, "modrinth", None),
            )
            report = await provider.search(query, minecraft_version=minecraft_version, loader=loader, limit=limit)
            reports.append(report)
        if output_dir:
            _write_source_search_report(reports, Path(output_dir))
        return reports

    async def source_inspect(
        self,
        source_ref: str,
        *,
        minecraft_version: str,
        loader: str,
        output_dir: Path | None = None,
    ):
        source, ref = _split_source_ref(source_ref)
        provider = provider_for_source(
            source,
            modrinth=getattr(self.facade, "modrinth", None),
        )
        candidate = await provider.inspect(ref, minecraft_version=minecraft_version, loader=loader)
        if output_dir and candidate is not None:
            _write_source_inspect_report(candidate, Path(output_dir))
        return candidate

    async def resolve_sources(
        self,
        selected: SelectedModList,
        *,
        sources: list[str] | None = None,
        target_export: str = "local_instance",
        autonomous: bool = True,
        allow_manual_sources: bool = False,
        output_dir: Path | None = None,
    ) -> SourceResolveReport:
        report = await resolve_sources_for_selected_mods(
            selected,
            minecraft_version=selected.minecraft_version,
            loader=selected.loader,
            sources=sources or ["modrinth"],
            target_export=target_export,
            autonomous=autonomous,
            modrinth=getattr(self.facade, "modrinth", None),
            allow_manual_sources=allow_manual_sources,
        )
        if output_dir:
            _write_source_resolve_report(report, Path(output_dir))
        return report

    async def verify_mod_list(self, selected: SelectedModList) -> AgentPackReport:
        user_selected, rejected = await self._hydrate_selected_mods(selected)
        fatal = [r for r in rejected if r.reason != "optional_not_resolved"]
        optional_msgs = [f"Optional row not resolved ({r.project_id}): {r.detail or r.reason}" for r in rejected if r.reason == "optional_not_resolved"]
        status = "failed" if fatal else "completed"
        memory_hints = self.memory.hints_for_candidates(user_selected, minecraft_version=selected.minecraft_version, loader=selected.loader)
        compat = list(memory_hints["warnings"]) + optional_msgs
        return self._report(
            selected,
            status=status,
            failed_stage="verify_list" if fatal else None,
            user_selected_mods=user_selected,
            selected_mods=user_selected,
            rejected_mods=fatal,
            incompatible_mods=[item for item in fatal if item.reason == "no_compatible_installable_version"],
            unresolved_mods=[item for item in fatal if item.reason == "project_not_found"],
            compatibility_warnings=compat,
            known_good_matches=memory_hints["known_good_matches"],
            known_risk_matches=memory_hints["known_risk_matches"],
            memory_confidence_adjustment=memory_hints["confidence_adjustment"],
        )

    async def resolve_mod_list(self, selected: SelectedModList) -> AgentPackReport:
        verified = await self.verify_mod_list(selected)
        if verified.status == "failed":
            return verified.model_copy(update={"failed_stage": "verify_list"})
        profile = _profile_from_selected(selected)
        expanded, dependency_rejections = await expand_required_dependencies(
            self.facade.modrinth,
            verified.user_selected_mods,
            profile,
            selected.minecraft_version,
        )
        requested_ids = [candidate.project_id for candidate in expanded]
        resolved = self.facade.resolve_dependencies(requested_ids, expanded, profile)
        memory_hints = self.memory.hints_for_candidates(
            verified.user_selected_mods,
            minecraft_version=selected.minecraft_version,
            loader=selected.loader,
        )
        compat_warnings = list(memory_hints["warnings"])

        seen_closure: set[str] = set()
        deduped_selected: list[CandidateMod] = []
        dup_closure: list[str] = []
        for mod in resolved.selected_mods:
            if mod.project_id in seen_closure:
                dup_closure.append(mod.project_id)
                continue
            seen_closure.add(mod.project_id)
            deduped_selected.append(mod)
        if dup_closure:
            resolved = resolved.model_copy(update={"selected_mods": deduped_selected})
            uniq = sorted(set(dup_closure))
            compat_warnings.append(
                "Resolved dependency closure listed the same Modrinth project more than once "
                f"(deduped): {', '.join(uniq)}"
            )

        rejected = dependency_rejections + resolved.rejected_mods
        dependency_added = [candidate for candidate in expanded if candidate.selection_type == "dependency_added"]
        status = "failed" if rejected else "completed"
        return self._report(
            selected,
            status=status,
            failed_stage="dependency_resolution" if rejected else None,
            user_selected_mods=verified.user_selected_mods,
            dependency_added_mods=dependency_added,
            selected_mods=resolved.selected_mods if not rejected else expanded,
            rejected_mods=rejected,
            missing_dependencies=[item for item in rejected if "dependency" in item.reason],
            unresolved_required_dependencies=[item for item in rejected if "dependency" in item.reason],
            transitive_dependency_count=len(dependency_added),
            dependency_source_breakdown={"modrinth": len(resolved.selected_mods if not rejected else expanded)},
            dependency_closure_passed=not rejected,
            dependency_edges=resolved.dependency_edges,
            compatibility_warnings=compat_warnings,
            known_good_matches=memory_hints["known_good_matches"],
            known_risk_matches=memory_hints["known_risk_matches"],
            memory_confidence_adjustment=memory_hints["confidence_adjustment"],
        )

    async def review_mod_list(
        self,
        selected: SelectedModList,
        output_dir: Path | None = None,
        *,
        write_prompt: bool = True,
        pack_design: PackDesign | None = None,
        pack_design_path: Path | str | None = None,
    ) -> SelectedModReviewReport:
        verified = await self.verify_mod_list(selected)
        candidates = verified.user_selected_mods
        removed_mods = list(verified.removed_mods)
        issues: list[ReviewIssue] = []
        duplicate_systems: list[ReviewIssue] = []
        risky_combinations: list[ReviewIssue] = []
        stale_or_low_signal_mods: list[ReviewIssue] = []
        novelty_or_off_theme_mods: list[ReviewIssue] = []
        dependency_impact = DependencyImpactReport(user_selected_count=len(candidates))

        for rejected in verified.rejected_mods + verified.incompatible_mods + verified.unresolved_mods:
            issues.append(
                ReviewIssue(
                    severity="critical",
                    category="installability",
                    title="Selected mod is not installable for the target",
                    detail=f"{rejected.reason}: {rejected.detail or ''}".strip(),
                    affected_mods=[rejected.project_id],
                    suggested_action="Replace or remove this mod before building.",
                    replacement_search_terms=[
                        f"Fabric {selected.minecraft_version} replacement for {rejected.project_id}",
                    ],
                )
            )

        if verified.status != "failed":
            profile = _profile_from_selected(selected)
            expanded, dependency_rejections = await expand_required_dependencies(
                self.facade.modrinth,
                candidates,
                profile,
                selected.minecraft_version,
            )
            resolved = self.facade.resolve_dependencies(
                [candidate.project_id for candidate in expanded],
                expanded,
                profile,
            )
            dependency_added = [candidate for candidate in expanded if candidate.selection_type == "dependency_added"]
            dependency_impact = DependencyImpactReport(
                user_selected_count=len(candidates),
                dependency_added_count=len(dependency_added),
                dependency_added_mods=[candidate.slug or candidate.project_id for candidate in dependency_added],
                missing_dependencies=dependency_rejections + resolved.rejected_mods,
                dependency_edges=resolved.dependency_edges,
            )
            if dependency_impact.missing_dependencies:
                issues.append(
                    ReviewIssue(
                        severity="critical",
                        category="dependency_impact",
                        title="Required dependencies could not be resolved",
                        affected_mods=[item.project_id for item in dependency_impact.missing_dependencies],
                        suggested_action="Replace mods with unresolved dependencies before building.",
                        replacement_search_terms=[f"Fabric {selected.minecraft_version} alternative with resolved dependencies"],
                    )
                )
            elif dependency_impact.dependency_added_count > max(3, len(candidates) // 2):
                issues.append(
                    ReviewIssue(
                        severity="warning",
                        category="dependency_impact",
                        title="Dependency impact is large before build",
                        detail=f"{dependency_impact.dependency_added_count} dependencies would be added.",
                        affected_mods=dependency_impact.dependency_added_mods,
                        suggested_action="Review whether selected mods pull in too much support code.",
                    )
                )

        pillars = _review_pillar_coverage(candidates, pack_design)
        for pillar in pillars:
            if pillar.pillar == "performance_foundation" and pillar.status == "missing":
                issues.append(
                    ReviewIssue(
                        severity="high",
                        category="pillar_coverage",
                        title="Missing performance foundation",
                        detail="No renderer, logic, memory, or entity-culling optimization mod was found.",
                        suggested_action="Add verified Fabric performance foundation mods before build.",
                        replacement_search_terms=pillar.suggested_search_terms,
                    )
                )
            elif pillar.status == "overloaded":
                issues.append(
                    ReviewIssue(
                        severity="warning",
                        category="pillar_coverage",
                        title=f"{pillar.pillar.replace('_', ' ').title()} is overloaded",
                        detail=pillar.detail,
                        affected_mods=pillar.matching_mods,
                        suggested_action="Trim overlapping mods from this pillar.",
                        replacement_search_terms=pillar.suggested_search_terms,
                    )
                )

        duplicate_systems = _review_duplicate_systems(candidates, selected.minecraft_version)
        memory_hints = self.memory.hints_for_candidates(candidates, minecraft_version=selected.minecraft_version, loader=selected.loader)
        risky_combinations = _review_memory_risks(memory_hints)
        stale_or_low_signal_mods = _review_stale_low_signal(candidates, selected.minecraft_version)
        novelty_or_off_theme_mods = _review_novelty_off_theme(candidates, selected)
        anti_goal_violations: list[ReviewIssue] = []
        progression_gaps: list[ReviewIssue] = []
        cohesion_issues: list[ReviewIssue] = []
        pacing_issues: list[ReviewIssue] = []
        config_or_datapack_warnings: list[ReviewIssue] = []
        system_coverage: dict[str, list[str]] = {}
        missing_required_systems: list[str] = []
        weak_required_systems: list[str] = []
        design_alignment_score = 0
        if pack_design is not None:
            (
                system_coverage,
                missing_required_systems,
                weak_required_systems,
                anti_goal_violations,
                progression_gaps,
                cohesion_issues,
                pacing_issues,
                config_or_datapack_warnings,
                design_alignment_score,
            ) = review_selected_mods_against_design(selected, candidates, pack_design)
            issues.extend(
                ReviewIssue(
                    severity="high" if system == "performance_foundation" else "high",
                    category="design_required_system",
                    title=f"Missing required design system: {system}",
                    detail=f"The selected list does not cover {system}.",
                    suggested_action=f"Add a verified mod that covers {system}.",
                    replacement_search_terms=[f"{selected.loader.title()} {selected.minecraft_version} {system.replace('_', ' ')}"],
                )
                for system in missing_required_systems
                if not any(issue.category == "design_required_system" and system in issue.title for issue in progression_gaps)
            )
            issues.extend(
                ReviewIssue(
                    severity="warning",
                    category="design_weak_system",
                    title=f"Thin required design system: {system}",
                    detail=f"Only one selected mod covers {system}; this may be fragile for {pack_design.archetype}.",
                    affected_mods=system_coverage.get(system, []),
                    suggested_action="Consider whether this system needs a stronger or clearer mod choice.",
                )
                for system in weak_required_systems
            )
        all_issues = (
            issues
            + duplicate_systems
            + risky_combinations
            + stale_or_low_signal_mods
            + novelty_or_off_theme_mods
            + anti_goal_violations
            + progression_gaps
            + cohesion_issues
            + pacing_issues
            + config_or_datapack_warnings
        )
        replacement_searches = _unique(
            term
            for issue in all_issues
            for term in issue.replacement_search_terms
            if term
        )
        base_score = _review_score(all_issues, pillars, dependency_impact)
        score = min(base_score, design_alignment_score) if pack_design is not None else base_score
        recommendation = _review_recommendation(score, all_issues)
        if pack_design is not None and design_alignment_score < 45:
            recommendation = "do_not_build"
        elif pack_design is not None and design_alignment_score < 70 and recommendation == "build":
            recommendation = "revise_first"
        elif (
            pack_design is not None
            and pack_design.archetype == "cozy_farming"
            and design_alignment_score >= 70
            and not any(issue.severity in {"critical", "high"} for issue in all_issues)
            and recommendation == "do_not_build"
        ):
            recommendation = "revise_first"
        report = SelectedModReviewReport(
            run_id=str(uuid.uuid4()),
            status={"build": "passed", "revise_first": "warnings", "do_not_build": "failed"}[recommendation],
            name=selected.name,
            summary=selected.summary,
            minecraft_version=selected.minecraft_version,
            loader=selected.loader,
            score=score,
            verdict=_review_verdict(recommendation),
            build_recommendation=recommendation,
            pillars=pillars,
            issues=issues,
            duplicate_systems=duplicate_systems,
            risky_combinations=risky_combinations,
            stale_or_low_signal_mods=stale_or_low_signal_mods,
            novelty_or_off_theme_mods=novelty_or_off_theme_mods,
            dependency_impact=dependency_impact,
            recommended_replacement_searches=replacement_searches,
            output_dir=str(output_dir) if output_dir else None,
            next_actions=_review_next_actions(recommendation, bool(write_prompt)),
            pack_design_path=str(pack_design_path) if pack_design_path else None,
            archetype=pack_design.archetype if pack_design else None,
            design_alignment_score=design_alignment_score,
            missing_required_systems=missing_required_systems,
            weak_required_systems=weak_required_systems,
            anti_goal_violations=anti_goal_violations,
            progression_gaps=progression_gaps,
            cohesion_issues=cohesion_issues,
            pacing_issues=pacing_issues,
            config_or_datapack_warnings=config_or_datapack_warnings,
            system_coverage=system_coverage,
            removed_mods=removed_mods,
        )
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            selected_snapshot = output_dir / "selected_mods.review_input.json"
            selected_snapshot.write_text(selected.model_dump_json(indent=2), encoding="utf-8")
            _write_removed_mods(removed_mods, output_dir)
            if write_prompt:
                prompt = write_cloud_ai_review_prompt(selected_snapshot, report, output_dir=output_dir)
                report.cloud_ai_prompt_path = str(prompt)
            _write_review_report(report, output_dir)
        return report

    async def build_from_list(
        self,
        selected: SelectedModList,
        output_dir: Path,
        *,
        download: bool = True,
        validate_launch: bool = False,
        force: bool = False,
        loader_version: str | None = None,
        memory_mb: int | None = None,
        sources: list[str] | None = None,
        target_export: str | None = None,
        auto_target: bool = False,
        candidate_versions: list[str] | None = None,
        candidate_loaders: list[str] | None = None,
        allow_manual_sources: bool = False,
    ) -> AgentPackReport:
        output_dir = Path(output_dir)
        gate = _blocking_review_report(output_dir)
        selected_snapshot = output_dir / "selected_mods.input.json"
        selected_snapshot.parent.mkdir(parents=True, exist_ok=True)
        selected_snapshot.write_text(selected.model_dump_json(indent=2), encoding="utf-8")
        if gate and not force:
            report = self._report(
                selected,
                status="failed",
                failed_stage="review_gate",
                compatibility_warnings=[gate],
                output_dir=str(output_dir),
                next_actions=["inspect_review_report", "rerun_review_list", "use_force_to_override_review_gate"],
            )
            _write_agent_report(report, output_dir)
            return report
        if sources is not None or target_export is not None or auto_target:
            return await self._build_from_list_sources(
                selected,
                output_dir,
                sources=sources or ["modrinth"],
                target_export=target_export or "local_instance",
                auto_target=auto_target,
                candidate_versions=candidate_versions,
                candidate_loaders=candidate_loaders,
                allow_manual_sources=allow_manual_sources,
                loader_version=loader_version,
            )
        resolved = await self.resolve_mod_list(selected)
        if resolved.status == "failed":
            resolved.output_dir = str(output_dir)
            resolved.dependency_closure_passed = False
            _write_agent_report(resolved, output_dir)
            _write_removed_mods(resolved.removed_mods, output_dir)
            write_cloud_ai_fix_selected_mods_prompt(
                selected_snapshot,
                output_dir=Path(output_dir),
                verify_report=resolved,
            )
            return resolved
        profile = _profile_from_selected(selected)
        pack = self.facade.resolve_dependencies(
            [candidate.project_id for candidate in resolved.selected_mods],
            resolved.selected_mods,
            profile,
            loader_version=loader_version,
        )
        build_pack_parameters = inspect.signature(self.facade.build_pack).parameters
        prefer_ids = frozenset({m.project_id for m in resolved.user_selected_mods})
        build_kwargs: dict[str, Any] = {"download": download, "artifact_prefer_project_ids": prefer_ids}
        if "memory_mb" in build_pack_parameters:
            build_kwargs["memory_mb"] = memory_mb
        artifacts = await self.facade.build_pack(pack, output_dir, **build_kwargs)
        warnings = list(resolved.compatibility_warnings)
        if gate and force:
            warnings.append(gate + " Forced build/export was requested.")
        artifact_report = getattr(self.facade, "last_final_artifact_validation_report", None) or {}
        artifact_ok = bool(getattr(self.facade, "last_final_artifact_validation_ok", True))
        artifact_path = Path(output_dir) / "final_artifact_validation_report.json"
        summary_bits = [
            f"artifact_validation_status={artifact_report.get('status', 'unknown')}",
            f"final_mod_count={artifact_report.get('final_mod_count')}",
            f"removed_duplicate_jars={len(artifact_report.get('removed_duplicate_jars') or [])}",
        ]
        artifact_summary = "; ".join(str(x) for x in summary_bits if x)
        if artifact_report.get("status") == "warnings":
            warnings.append(
                "Final mods-folder validation reported warnings (inspect final_artifact_validation_report.json for missing fabric.mod.json entries)."
            )
        if not artifact_ok:
            warnings.append("Final artifact validation FAILED; modpack export was aborted before writing .mrpack / Prism instance.")
            report = resolved.model_copy(
                update={
                    "status": "failed",
                    "failed_stage": "final_artifact_validation",
                    "generated_artifacts": artifacts,
                    "artifacts": artifacts,
                    "output_dir": str(output_dir),
                    "compatibility_warnings": warnings,
                    "next_actions": ["inspect_final_artifact_validation_report", "fix_selected_mods", "rebuild"],
                    "final_artifact_validation_status": str(artifact_report.get("status") or "failed"),
                    "final_artifact_validation_report_path": str(artifact_path) if artifact_path.is_file() else None,
                    "final_artifact_validation_summary": artifact_summary,
                }
            )
            _write_agent_report(report, output_dir)
            _write_removed_mods(report.removed_mods, output_dir)
            return report
        report = resolved.model_copy(
            update={
                "generated_artifacts": artifacts,
                "artifacts": artifacts,
                "output_dir": str(output_dir),
                "compatibility_warnings": warnings,
                "next_actions": ["inspect_report", "validate_launch"],
                "final_artifact_validation_status": str(artifact_report.get("status") or ("skipped" if not download else "passed")),
                "final_artifact_validation_report_path": str(artifact_path) if artifact_path.is_file() else None,
                "final_artifact_validation_summary": artifact_summary,
            }
        )
        if validate_launch:
            validation = await self.validate_pack(output_dir, pack_name=selected.name, force_validation=True)
            updates = _memory_updates_for_validation(validation)
            if validation.status == "passed":
                self.memory.record_successful_pack(
                    name=selected.name,
                    minecraft_version=selected.minecraft_version,
                    loader=selected.loader,
                    mods=[mod.slug for mod in report.user_selected_mods],
                    dependency_added_mods=[mod.slug for mod in report.dependency_added_mods],
                    validation_status=validation.status,
                    notes=validation.details or "Automatic launch validation passed.",
                )
            elif validation.status == "failed":
                analysis = validation.analysis
                self.memory.record_failed_pack(
                    name=selected.name,
                    minecraft_version=selected.minecraft_version,
                    loader=selected.loader,
                    mods=[mod.slug for mod in report.selected_mods],
                    failed_stage="validation_launch",
                    crash_classification=analysis.classification if analysis else "unknown",
                    suspected_mods=validation.suspected_mods,
                    suggested_fixes=validation.suggested_actions,
                    log_paths=validation.logs_collected,
                )
            report = report.model_copy(
                update={
                    "validation_status": validation.status,
                    "launch_validation": validation,
                    "logs_collected": validation.logs_collected,
                    "crash_analysis": validation.analysis,
                    "compatibility_memory_updates": updates,
                    "next_actions": _next_actions_after_validation(validation),
                }
            )
        _write_agent_report(report, output_dir)
        _write_removed_mods(report.removed_mods, output_dir)
        return report

    async def _build_from_list_sources(
        self,
        selected: SelectedModList,
        output_dir: Path,
        *,
        sources: list[str],
        target_export: str,
        auto_target: bool,
        candidate_versions: list[str] | None,
        candidate_loaders: list[str] | None,
        allow_manual_sources: bool,
        loader_version: str | None,
    ) -> AgentPackReport:
        working = selected.model_copy(deep=True)
        artifacts: list[BuildArtifact] = []
        warnings: list[str] = []
        if auto_target and (working.minecraft_version in {"auto", "any"} or working.loader in {"auto", "any"}):
            matrix = await build_target_matrix(
                working,
                sources=sources,
                candidate_versions=candidate_versions,
                candidate_loaders=candidate_loaders,
                target_export=target_export,
                facade=self.facade,
                allow_manual_sources=allow_manual_sources,
            )
            (output_dir / "target_matrix_report.json").write_text(matrix.model_dump_json(indent=2), encoding="utf-8")
            artifacts.append(BuildArtifact(kind="target-matrix-report", path=str(output_dir / "target_matrix_report.json")))
            if matrix.best is None or matrix.status == "failed":
                report = self._report(
                    working,
                    status="failed",
                    failed_stage="target_negotiation",
                    generated_artifacts=artifacts,
                    artifacts=artifacts,
                    compatibility_warnings=matrix.warnings,
                    output_dir=str(output_dir),
                    next_actions=["inspect_target_matrix_report", "constrain_minecraft_version_or_loader"],
                )
                _write_agent_report(report, output_dir)
                return report
            working.minecraft_version = matrix.best.minecraft_version
            working.loader = matrix.best.loader
            warnings.extend(matrix.best.warnings)

        source_report = await self.resolve_sources(
            working,
            sources=sources,
            target_export=target_export,
            autonomous=not allow_manual_sources,
            allow_manual_sources=allow_manual_sources,
            output_dir=output_dir,
        )
        blockers = list(source_report.export_blockers)
        if source_report.status == "failed" or blockers or not source_report.export_supported:
            report = self._report(
                working,
                status="failed",
                failed_stage="source_resolution",
                generated_artifacts=artifacts,
                artifacts=artifacts,
                compatibility_warnings=warnings + source_report.warnings + blockers,
                unresolved_required_dependencies=source_report.unresolved_required_dependencies,
                manually_required_dependencies=source_report.manually_required_dependencies,
                dependency_source_breakdown=source_report.dependency_source_breakdown,
                dependency_closure_passed=source_report.dependency_closure_passed,
                output_dir=str(output_dir),
                next_actions=["inspect_source_resolve_report", "replace_blocked_sources", "choose_compatible_export_target"],
            )
            _write_agent_report(report, output_dir)
            return report

        if target_export == "curseforge_manifest":
            artifact = build_curseforge_manifest(
                source_report,
                output_dir / f"{safe_slug(working.name, fallback='mythweaver-pack')}-curseforge.zip",
                name=working.name,
                version="1.0.0",
                author="MythWeaver",
                loader_version=loader_version,
            )
            artifacts.append(artifact)
            report = self._report(
                working,
                status="completed",
                generated_artifacts=artifacts,
                artifacts=artifacts,
                dependency_source_breakdown=source_report.dependency_source_breakdown,
                dependency_closure_passed=source_report.dependency_closure_passed,
                transitive_dependency_count=source_report.transitive_dependency_count,
                compatibility_warnings=warnings + source_report.warnings,
                output_dir=str(output_dir),
                next_actions=["import_curseforge_manifest"],
            )
            _write_agent_report(report, output_dir)
            return report

        if target_export in {"prism_instance", "local_instance", "multimc_instance"}:
            artifact = build_source_instance(
                source_report,
                output_dir / "instances",
                name=working.name,
                loader_version=loader_version,
                user_agent=getattr(getattr(self.facade, "settings", None), "modrinth_user_agent", "MythWeaver"),
                prism=target_export != "local_instance",
            )
            artifacts.append(artifact)
            report = self._report(
                working,
                status="completed",
                generated_artifacts=artifacts,
                artifacts=artifacts,
                dependency_source_breakdown=source_report.dependency_source_breakdown,
                dependency_closure_passed=source_report.dependency_closure_passed,
                transitive_dependency_count=source_report.transitive_dependency_count,
                compatibility_warnings=warnings + source_report.warnings,
                output_dir=str(output_dir),
                next_actions=["validate_launch"],
            )
            _write_agent_report(report, output_dir)
            return report

        report = self._report(
            working,
            status="failed",
            failed_stage="source_export",
            generated_artifacts=artifacts,
            artifacts=artifacts,
            compatibility_warnings=warnings
            + source_report.warnings
            + [f"{target_export} source-aware export is resolved but not yet buildable without downloader integration."],
            dependency_source_breakdown=source_report.dependency_source_breakdown,
            dependency_closure_passed=source_report.dependency_closure_passed,
            output_dir=str(output_dir),
            next_actions=["use_curseforge_manifest_or_existing_modrinth_build", "inspect_source_resolve_report"],
        )
        _write_agent_report(report, output_dir)
        return report

    async def agent_check(
        self,
        selected: SelectedModList,
        output_dir: Path | None = None,
        *,
        write_prompt: bool = True,
        pack_design: PackDesign | None = None,
        pack_design_path: Path | str | None = None,
        sources: list[str] | None = None,
        target_export: str = "modrinth_pack",
        allow_manual_sources: bool = False,
    ) -> AgentCheckReport:
        target = Path(output_dir) if output_dir else None
        review = await self.review_mod_list(
            selected,
            target,
            write_prompt=False,
            pack_design=pack_design,
            pack_design_path=pack_design_path,
        )
        hard_blockers: list[AgentCheckFinding] = []
        warnings: list[AgentCheckFinding] = []
        ai_judgment_needed: list[AgentCheckFinding] = []

        for issue in review.issues:
            finding = _agent_finding_from_issue(issue)
            if finding.kind in {"technical_blocker", "dependency_issue"} or finding.severity == "critical":
                hard_blockers.append(finding)
            elif finding.kind in {"performance_signal", "stale_or_low_signal", "compatibility_risk"}:
                warnings.append(finding)
            else:
                ai_judgment_needed.append(finding)

        for issue in review.risky_combinations:
            finding = _agent_finding_from_issue(issue, kind="compatibility_risk", confidence="high")
            if issue.severity == "critical":
                hard_blockers.append(finding)
            else:
                warnings.append(finding)

        for issue in review.stale_or_low_signal_mods:
            warnings.append(_agent_finding_from_issue(issue, kind="stale_or_low_signal", confidence="medium"))

        for removed in review.removed_mods:
            hard_blockers.append(
                AgentCheckFinding(
                    severity="critical",
                    kind="removed_mod",
                    title="Selected mod was removed or rejected during verification",
                    detail=removed.reason,
                    affected_mods=[removed.slug_or_id],
                    confidence="high",
                    ai_instruction="Replace this mod with a real compatible Modrinth project or remove it intentionally.",
                    suggested_search_terms=removed.replacement_search_terms,
                )
            )

        subjective_groups = (
            review.duplicate_systems
            + review.novelty_or_off_theme_mods
            + review.cohesion_issues
            + review.pacing_issues
            + review.config_or_datapack_warnings
        )
        for issue in subjective_groups:
            ai_judgment_needed.append(_agent_finding_from_issue(issue, kind=_agent_kind_for_subjective(issue), confidence="low"))

        for issue in review.anti_goal_violations:
            finding = _agent_finding_from_issue(issue, kind="theme_signal", confidence="high")
            if issue.severity in {"high", "critical"}:
                hard_blockers.append(
                    finding.model_copy(
                        update={
                            "kind": "technical_blocker",
                            "ai_instruction": "This violates an explicit design anti-goal. Remove or replace unless the user changes the design.",
                        }
                    )
                )
            else:
                ai_judgment_needed.append(finding)

        for issue in review.progression_gaps:
            ai_judgment_needed.append(_agent_finding_from_issue(issue, kind="theme_signal", confidence="medium"))

        for missing in review.missing_required_systems:
            if missing == "performance_foundation":
                warnings.append(
                    AgentCheckFinding(
                        severity="high",
                        kind="performance_signal",
                        title="Missing performance foundation",
                        detail="Performance foundation is recommended, but this is not a build blocker unless the user requires it or the pack is large/heavy.",
                        affected_mods=[],
                        confidence="high",
                        ai_instruction="Usually add Sodium/Lithium/FerriteCore-style performance support for Fabric packs.",
                        suggested_search_terms=[f"{selected.loader.title()} {selected.minecraft_version} performance foundation"],
                    )
                )

        if sources or any(entry.source != "auto" for entry in selected.mods):
            source_report = await self.resolve_sources(
                selected,
                sources=sources or ["modrinth"],
                target_export=target_export,
                autonomous=not allow_manual_sources,
                allow_manual_sources=allow_manual_sources,
            )
            for candidate in source_report.manual_required + source_report.blocked + source_report.manually_required_dependencies:
                finding = AgentCheckFinding(
                    severity="high" if candidate in source_report.blocked else "warning",
                    kind="technical_blocker",
                    title="Source acquisition is not fully automated",
                    detail=f"{candidate.source}:{candidate.slug or candidate.project_id or candidate.name} is {candidate.acquisition_status}.",
                    affected_mods=[candidate.slug or candidate.project_id or candidate.name],
                    confidence="high",
                    ai_instruction="Choose a verified_auto source alternative or explicitly switch to manual/local validation mode.",
                    suggested_search_terms=[f"{selected.loader.title()} {selected.minecraft_version} verified alternative for {candidate.name}"],
                )
                if candidate in source_report.blocked:
                    hard_blockers.append(finding)
                else:
                    warnings.append(finding)
            for dependency in source_report.unresolved_required_dependencies:
                hard_blockers.append(
                    AgentCheckFinding(
                        severity="critical",
                        kind="dependency_issue",
                        title="Required dependency closure failed",
                        detail=dependency.detail or dependency.reason,
                        affected_mods=[dependency.project_id],
                        confidence="high",
                        ai_instruction="Replace/remove the requiring mod or choose a version/source whose required dependencies are acquirable.",
                        suggested_search_terms=[f"{selected.loader.title()} {selected.minecraft_version} alternative for {dependency.project_id}"],
                    )
                )
            if target:
                _write_source_resolve_report(source_report, target)

        hard_blockers = _dedupe_findings(hard_blockers)
        warnings = _dedupe_findings(warnings)
        ai_judgment_needed = _dedupe_findings(ai_judgment_needed)
        replacement_searches = _unique(
            term
            for finding in hard_blockers + warnings + ai_judgment_needed
            for term in finding.suggested_search_terms
            if term
        )
        has_hard_blockers = bool(hard_blockers or review.dependency_impact.missing_dependencies)
        build_permission = "blocked" if has_hard_blockers else ("allowed_with_warnings" if warnings or ai_judgment_needed else "allowed")
        status = "blocked" if build_permission == "blocked" else ("needs_ai_revision" if build_permission == "allowed_with_warnings" else "ok")
        report = AgentCheckReport(
            name=selected.name,
            minecraft_version=selected.minecraft_version,
            loader=selected.loader,
            status=status,
            build_permission=build_permission,
            summary=_agent_check_summary(build_permission, hard_blockers, warnings, ai_judgment_needed),
            hard_blockers=hard_blockers,
            warnings=warnings,
            ai_judgment_needed=ai_judgment_needed,
            dependency_summary=review.dependency_impact,
            removed_mods=review.removed_mods,
            suggested_replacement_searches=replacement_searches,
            next_recommended_steps=_agent_check_next_steps(build_permission),
            output_dir=str(target) if target else None,
        )
        if target:
            target.mkdir(parents=True, exist_ok=True)
            selected_snapshot = target / "selected_mods.agent_check_input.json"
            selected_snapshot.write_text(selected.model_dump_json(indent=2), encoding="utf-8")
            if write_prompt:
                prompt = write_cloud_ai_agent_repair_prompt(selected_snapshot, report, output_dir=target)
                report.cloud_ai_prompt_path = str(prompt)
            _write_agent_check_report(report, target)
        return report

    async def agent_pack(
        self,
        selected: SelectedModList,
        output_dir: Path | None = None,
        *,
        download: bool = True,
        validate_launch: bool = False,
        force: bool = False,
        sources: list[str] | None = None,
        target_export: str | None = None,
        auto_target: bool = False,
        candidate_versions: list[str] | None = None,
        candidate_loaders: list[str] | None = None,
        allow_manual_sources: bool = False,
        loader_version: str | None = None,
    ) -> AgentPackReport:
        target = output_dir or Path("output") / "generated" / safe_slug(selected.name, fallback="agent-pack")
        return await self.build_from_list(
            selected,
            target,
            download=download,
            validate_launch=validate_launch,
            force=force,
            sources=sources,
            target_export=target_export,
            auto_target=auto_target,
            candidate_versions=candidate_versions,
            candidate_loaders=candidate_loaders,
            allow_manual_sources=allow_manual_sources,
            loader_version=loader_version,
        )

    async def build_verify_and_repair_pack(
        self,
        selected: SelectedModList,
        output_root: Path,
        *,
        sources: list[str] | None = None,
        target_export: str = "local_instance",
        minecraft_version: str = "auto",
        loader: str = "auto",
        loader_version: str | None = None,
        candidate_versions: list[str] | None = None,
        candidate_loaders: list[str] | None = None,
        max_attempts: int = 5,
        memory_mb: int = 4096,
        timeout_seconds: int = 180,
        java_path: str | None = None,
        allow_manual_sources: bool = False,
        allow_target_switch: bool = True,
        allow_loader_switch: bool = True,
        allow_minecraft_version_switch: bool = True,
        allow_remove_content_mods: bool = False,
        keep_failed_instances: bool = False,
        inject_smoke_test: bool = True,
        smoke_test_helper_path: str | None = None,
        require_smoke_test_proof: bool = True,
        minimum_stability_seconds: int = 60,
        run_id: str | None = None,
        resume_run_id: str | None = None,
    ) -> AutopilotReport:
        output_root = Path(output_root)
        output_root.mkdir(parents=True, exist_ok=True)
        selected_path = output_root / "selected_mods.autopilot_input.json"
        selected_path.write_text(selected.model_dump_json(indent=2), encoding="utf-8")
        return await run_autopilot(
            AutopilotRequest(
                selected_mods_path=str(selected_path),
                sources=sources or ["modrinth", "curseforge"],
                run_id=run_id,
                resume_run_id=resume_run_id,
                target_export=target_export,
                minecraft_version=minecraft_version,
                loader=loader,
                loader_version=loader_version,
                candidate_versions=candidate_versions or [],
                candidate_loaders=candidate_loaders or [],
                max_attempts=max_attempts,
                memory_mb=memory_mb,
                timeout_seconds=timeout_seconds,
                output_root=str(output_root),
                java_path=java_path,
                allow_manual_sources=allow_manual_sources,
                allow_target_switch=allow_target_switch,
                allow_loader_switch=allow_loader_switch,
                allow_minecraft_version_switch=allow_minecraft_version_switch,
                allow_remove_content_mods=allow_remove_content_mods,
                keep_failed_instances=keep_failed_instances,
                inject_smoke_test=inject_smoke_test,
                smoke_test_helper_path=smoke_test_helper_path,
                require_smoke_test_proof=require_smoke_test_proof,
                minimum_stability_seconds=minimum_stability_seconds,
            )
        )

    async def analyze_crash(
        self,
        crash_text: str,
        *,
        selected: SelectedModList | None = None,
        selected_mods_path: str | None = None,
        crash_report_path: str | None = None,
        output_dir: Path | None = None,
    ) -> CrashAnalysisReport:
        report = analyze_crash_report(crash_text, selected=selected, crash_report_path=crash_report_path)
        if selected is not None:
            report.selected_mods_path = selected_mods_path
        if output_dir:
            target = Path(output_dir)
            target.mkdir(parents=True, exist_ok=True)
            report.output_dir = str(target)
            prompt = write_cloud_ai_crash_repair_prompt(report, output_dir=target)
            report.cloud_ai_prompt_path = str(prompt)
            _write_crash_analysis_report(report, target)
        return report

    async def setup_launcher(
        self,
        pack_artifact: Path,
        output_dir: Path,
        *,
        launcher: str,
        instance_name: str,
        minecraft_version: str,
        loader: str,
        loader_version: str | None,
        memory_mb: int,
        validate_only: bool = False,
        instance_path: Path | None = None,
    ) -> tuple[LauncherInstanceReport, LauncherValidationReport]:
        instance, validation = setup_launcher_instance(
            pack_artifact,
            launcher=launcher,
            instance_name=instance_name,
            minecraft_version=minecraft_version,
            loader=loader,
            loader_version=loader_version,
            memory_mb=memory_mb,
            output_dir=output_dir,
            validate_only=validate_only,
            instance_path=instance_path,
            env=_launcher_env_from_settings(self.settings),
        )
        write_launcher_reports(instance=instance, validation=validation, output_dir=output_dir)
        return instance, validation

    async def launcher_launch_check(
        self,
        *,
        launcher: str,
        instance_path: Path | None,
        wait_seconds: int,
        output_dir: Path,
        selected: SelectedModList | None = None,
        crash_report: Path | None = None,
        latest_log: Path | None = None,
        inject_smoke_test: bool = False,
        validation_world: bool = False,
        keep_validation_world: bool = False,
    ) -> RuntimeSmokeTestReport:
        report = run_launch_check(
            launcher=launcher,
            instance_path=instance_path,
            wait_seconds=wait_seconds,
            output_dir=output_dir,
            selected=selected,
            crash_report=crash_report,
            latest_log=latest_log,
            inject_smoke_test=inject_smoke_test,
            validation_world=validation_world,
            keep_validation_world=keep_validation_world,
            env=_launcher_env_from_settings(self.settings),
        )
        write_runtime_smoke_report(report, output_dir)
        return report

    async def launch_check(
        self,
        selected: SelectedModList,
        pack_dir: Path,
        *,
        manual: bool = False,
        crash_report: Path | None = None,
    ) -> LaunchValidationReport:
        pack_dir = Path(pack_dir)
        pack_dir.mkdir(parents=True, exist_ok=True)
        if crash_report:
            crash_path = Path(crash_report)
            analysis = await self.analyze_crash(
                crash_path.read_text(encoding="utf-8", errors="replace"),
                selected=selected,
                crash_report_path=str(crash_path),
                output_dir=pack_dir,
            )
            report = LaunchValidationReport(
                status="failed",
                stage="world_join" if any(finding.kind == "world_join_crash" for finding in analysis.findings) else "game_start",
                summary="Launch/runtime validation failed from supplied crash report. Dry-run is not playable proof.",
                crash_report_path=str(crash_path),
                crash_analysis=analysis,
                output_dir=str(pack_dir),
            )
            _write_launch_validation_report(report, pack_dir)
            return report
        if manual:
            report = LaunchValidationReport(
                status="manual_required",
                stage="not_started",
                summary="Dry-run is not playable proof. Launch Minecraft and enter a world, then provide a crash report if it fails.",
                output_dir=str(pack_dir),
            )
            _write_launch_validation_report(report, pack_dir)
            return report
        validation = await self.validate_pack(pack_dir, pack_name=selected.name, force_validation=True)
        if validation.status == "passed":
            status = "passed"
            stage = "complete"
            summary = "Launch validation passed."
        elif validation.status in {"failed", "timeout"}:
            status = "failed"
            stage = "runtime_wait"
            summary = validation.details or "Launch validation failed."
        else:
            status = "manual_required"
            stage = "launcher_setup"
            summary = "Launch automation is unavailable. Dry-run is not playable proof; manual launch validation is required."
        crash_analysis = None
        if validation.crash_report_path and Path(validation.crash_report_path).is_file():
            crash_analysis = await self.analyze_crash(
                Path(validation.crash_report_path).read_text(encoding="utf-8", errors="replace"),
                selected=selected,
                crash_report_path=validation.crash_report_path,
                output_dir=pack_dir,
            )
        report = LaunchValidationReport(
            status=status,
            stage=stage,
            summary=summary,
            crash_report_path=validation.crash_report_path,
            crash_analysis=crash_analysis,
            log_path=validation.latest_log_path or validation.log_path,
            output_dir=str(pack_dir),
        )
        _write_launch_validation_report(report, pack_dir)
        return report

    async def stabilize_pack(
        self,
        selected: SelectedModList,
        output_dir: Path,
        *,
        pack_design: PackDesign | None = None,
        pack_design_path: Path | str | None = None,
        max_attempts: int = 3,
        manual_crash_report: Path | None = None,
        no_launch: bool = False,
        prefer_remove_risky_optionals: bool = True,
    ) -> StabilizationReport:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        attempts: list[StabilizationAttempt] = []
        current = selected
        all_removed: list[RemovedSelectedMod] = []
        unresolved: list[CrashFinding] = []
        previous_written = False
        max_attempts = max(1, max_attempts)

        for attempt_number in range(1, max_attempts + 1):
            selected_path = output_dir / ("selected_mods.input.json" if attempt_number == 1 else f"selected_mods.attempt{attempt_number}.json")
            selected_path.write_text(current.model_dump_json(indent=2), encoding="utf-8")
            await self.agent_check(
                current,
                output_dir,
                write_prompt=True,
                pack_design=pack_design,
                pack_design_path=pack_design_path,
            )
            verify = await self.verify_mod_list(current)
            verify_status = "passed" if verify.status != "failed" else "failed"
            dry_run = await self.build_from_list(current, output_dir, download=False, force=True)
            dry_run_status = "passed" if dry_run.status == "completed" else "failed"

            launch = await self.launch_check(
                current,
                output_dir,
                manual=no_launch and manual_crash_report is None,
                crash_report=manual_crash_report if attempt_number == 1 else None,
            )
            removed_this_attempt: list[RemovedSelectedMod] = []
            changes: list[str] = []
            if launch.status == "failed" and launch.crash_analysis:
                self.memory.record_failed_pack(
                    name=current.name,
                    minecraft_version=current.minecraft_version,
                    loader=current.loader,
                    mods=[entry.identifier() for entry in current.mods],
                    failed_stage="runtime_launch",
                    crash_classification=launch.crash_analysis.findings[0].kind if launch.crash_analysis.findings else "unknown",
                    suspected_mods=_crash_suspects(launch.crash_analysis),
                    suggested_fixes=[
                        action
                        for finding in launch.crash_analysis.findings
                        for action in finding.suggested_actions
                    ],
                    log_paths=[launch.crash_report_path] if launch.crash_report_path else [],
                )
                if prefer_remove_risky_optionals:
                    repaired, removed_this_attempt = _repair_selected_for_runtime_crash(current, launch.crash_analysis)
                    if removed_this_attempt:
                        if not previous_written:
                            (output_dir / "selected_mods.previous.json").write_text(selected.model_dump_json(indent=2), encoding="utf-8")
                            previous_written = True
                        current = repaired
                        all_removed.extend(removed_this_attempt)
                        changes = [f"Removed {item.slug_or_id}: {item.reason}" for item in removed_this_attempt]
                    else:
                        unresolved.extend(launch.crash_analysis.findings)
            attempts.append(
                StabilizationAttempt(
                    attempt_number=attempt_number,
                    selected_mods_path=str(selected_path),
                    verify_status=verify_status,
                    dry_run_status=dry_run_status,
                    launch_status=launch.status,
                    crash_summary=launch.crash_analysis.summary if launch.crash_analysis else None,
                    changes_made=changes,
                    removed_mods=removed_this_attempt,
                )
            )
            if verify_status == "failed" or dry_run_status == "failed":
                break
            if launch.status == "passed":
                stabilized_path = output_dir / "selected_mods.stabilized.json"
                stabilized_path.write_text(current.model_dump_json(indent=2), encoding="utf-8")
                report = StabilizationReport(
                    name=current.name,
                    status="stable",
                    summary="Pack passed verification, dry-run, and launch validation.",
                    attempts=attempts,
                    final_selected_mods_path=str(stabilized_path),
                    final_output_dir=str(output_dir),
                    unresolved_findings=[],
                    output_dir=str(output_dir),
                )
                _write_stabilization_outputs(report, output_dir, all_removed)
                return report
            if removed_this_attempt and attempt_number < max_attempts and not no_launch:
                continue
            break

        stabilized_path = output_dir / "selected_mods.stabilized.json"
        stabilized_path.write_text(current.model_dump_json(indent=2), encoding="utf-8")
        status = "needs_manual_review" if attempts and attempts[-1].launch_status == "manual_required" or all_removed else "failed"
        summary = (
            "Runtime repair was applied; launch/world-join validation is still required."
            if all_removed
            else "Stabilization stopped before runtime stability could be proven."
        )
        report = StabilizationReport(
            name=current.name,
            status=status,
            summary=summary,
            attempts=attempts,
            final_selected_mods_path=str(stabilized_path),
            final_output_dir=str(output_dir),
            unresolved_findings=unresolved,
            output_dir=str(output_dir),
        )
        _write_stabilization_outputs(report, output_dir, all_removed)
        return report

    async def autonomous_build(
        self,
        concept_path: Path,
        output_dir: Path,
        *,
        selected: SelectedModList | None = None,
        launcher: str = "prism",
        loader_version: str | None = None,
        memory_mb: int = 8192,
        max_attempts: int = 3,
        wait_seconds: int = 120,
        no_launch: bool = False,
        manual_crash_report: Path | None = None,
        sources: list[str] | None = None,
        allow_manual_sources: bool = False,
        target_export: str = "local_instance",
        inject_smoke_test_mod: bool = True,
        validation_world: bool = True,
        keep_validation_world: bool = False,
    ) -> AutonomousBuildReport:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        concept_path = Path(concept_path)
        concept_text = concept_path.read_text(encoding="utf-8", errors="replace") if concept_path.is_file() else ""
        name = _concept_name_for_autonomous(concept_path, concept_text, selected)
        attempts: list[AutonomousBuildAttempt] = []
        current = selected
        all_removed: list[RemovedSelectedMod] = []
        final_pack_artifact: str | None = None
        final_instance_path: str | None = None
        max_attempts = max(1, max_attempts)
        loader_version = loader_version or ("0.19.2" if (current is None or current.loader == "fabric") else None)

        if current is None:
            from mythweaver.handoff import write_agent_workflow_prompt

            prompt_report = write_agent_workflow_prompt(concept_path, concept_text, output_dir=output_dir)
            report = AutonomousBuildReport(
                name=name,
                status="needs_manual_review",
                summary="Creative selected_mods.json is required. MythWeaver wrote an agent workflow prompt instead of inventing mod choices.",
                attempts=[],
                output_dir=str(output_dir),
                user_next_steps=[f"Use {prompt_report.prompt_path} with Cursor/Codex to create selected_mods.json."],
            )
            _write_autonomous_build_report(report, output_dir)
            return report

        if sources is not None or any(entry.source != "auto" for entry in current.mods):
            source_report = await self.resolve_sources(
                current,
                sources=sources or ["modrinth"],
                target_export=target_export,
                autonomous=True,
                allow_manual_sources=allow_manual_sources,
                output_dir=output_dir,
            )
            source_blockers = list(source_report.blocked)
            unresolved_dependency_blockers = list(source_report.unresolved_required_dependencies)
            if not allow_manual_sources:
                source_blockers.extend(source_report.manual_required)
                source_blockers.extend(source_report.manually_required_dependencies)
            if source_blockers or unresolved_dependency_blockers or not source_report.dependency_closure_passed:
                final_selected = output_dir / "selected_mods.final.json"
                final_selected.write_text(current.model_dump_json(indent=2), encoding="utf-8")
                report = AutonomousBuildReport(
                    name=current.name,
                    status="needs_manual_review",
                    summary="Autonomous build stopped because one or more selected mods require manual, incomplete, blocked, or unsafe source acquisition.",
                    attempts=[],
                    final_selected_mods_path=str(final_selected),
                    output_dir=str(output_dir),
                    user_next_steps=[
                        "Replace manual or incomplete sources with verified_auto alternatives.",
                        "Use source-resolve to review source acquisition before building.",
                        "Manual sources require explicit approval plus local verification before launcher/runtime stability can be claimed.",
                    ],
                )
                _write_autonomous_build_report(report, output_dir)
                return report

        for attempt_number in range(1, max_attempts + 1):
            attempt_selected_path = output_dir / f"selected_mods.attempt-{attempt_number}.json"
            attempt_selected_path.write_text(current.model_dump_json(indent=2), encoding="utf-8")
            build = await self.build_from_list(
                current,
                output_dir / f"attempt-{attempt_number}",
                download=not no_launch,
                force=True,
                loader_version=loader_version,
                memory_mb=memory_mb,
            )
            build_report_path = str(Path(build.output_dir or output_dir / f"attempt-{attempt_number}") / "generation_report.json")
            pack_artifacts = [artifact.path for artifact in build.generated_artifacts if artifact.kind == "mrpack"]
            prism_instances = [artifact.path for artifact in build.generated_artifacts if artifact.kind == "prism-instance"]
            final_pack_artifact = pack_artifacts[0] if pack_artifacts else final_pack_artifact
            final_instance_path = prism_instances[0] if prism_instances else final_instance_path
            pack_artifact_path = Path(final_pack_artifact or output_dir / f"{safe_slug(current.name, fallback='pack')}.mrpack")
            instance_report, launcher_validation = await self.setup_launcher(
                pack_artifact_path,
                output_dir / f"attempt-{attempt_number}",
                launcher=launcher,
                instance_name=current.name,
                minecraft_version=current.minecraft_version,
                loader=current.loader,
                loader_version=loader_version,
                memory_mb=memory_mb,
                validate_only=bool(final_instance_path),
                instance_path=Path(final_instance_path) if final_instance_path else None,
            )
            final_instance_path = instance_report.instance_path or final_instance_path
            runtime = await self.launcher_launch_check(
                launcher=launcher,
                instance_path=Path(instance_report.instance_path) if instance_report.instance_path else None,
                wait_seconds=wait_seconds,
                output_dir=output_dir / f"attempt-{attempt_number}",
                selected=current,
                crash_report=manual_crash_report if attempt_number == 1 else None,
                inject_smoke_test=inject_smoke_test_mod and not no_launch and launcher in {"auto", "prism", "prismlauncher", "prism-launcher", "multimc"},
                validation_world=validation_world and not no_launch and launcher in {"auto", "prism", "prismlauncher", "prism-launcher", "multimc"},
                keep_validation_world=keep_validation_world,
            )
            removed_this_attempt: list[RemovedSelectedMod] = []
            changes: list[str] = []
            if runtime.status == "failed" and runtime.crash_analysis:
                repaired, removed_this_attempt = _repair_selected_for_runtime_crash(current, runtime.crash_analysis)
                if removed_this_attempt:
                    current = repaired
                    all_removed.extend(removed_this_attempt)
                    changes = [f"Removed {item.slug_or_id}: {item.reason}" for item in removed_this_attempt]
            attempts.append(
                AutonomousBuildAttempt(
                    attempt_number=attempt_number,
                    selected_mods_path=str(attempt_selected_path),
                    build_report_path=build_report_path,
                    launcher_instance_report=instance_report,
                    launcher_validation_report=launcher_validation,
                    runtime_smoke_test_report=runtime,
                    changes_made=changes,
                    removed_mods=removed_this_attempt,
                )
            )
            if (
                build.status == "completed"
                and launcher_validation.status == "passed"
                and runtime.status == "passed"
                and runtime.runtime_proof_observed
                and runtime.required_markers_met
            ):
                final_selected = output_dir / "selected_mods.final.json"
                final_selected.write_text(current.model_dump_json(indent=2), encoding="utf-8")
                report = AutonomousBuildReport(
                    name=current.name,
                    status="stable",
                    summary="Pack passed build, launcher validation, and runtime smoke test.",
                    attempts=attempts,
                    final_selected_mods_path=str(final_selected),
                    final_instance_path=final_instance_path,
                    final_pack_artifact_path=final_pack_artifact,
                    output_dir=str(output_dir),
                    final_status_reason="runtime_smoke_test_passed",
                    runtime_proof_required=True,
                    runtime_proof_observed=True,
                    smoke_test_mod_used=runtime.smoke_test_mod_injected,
                    stability_seconds_proven=runtime.stability_seconds_proven,
                    user_next_steps=[],
                )
                _write_autonomous_build_report(report, output_dir)
                return report
            if removed_this_attempt and attempt_number < max_attempts and not no_launch:
                continue
            break

        final_selected = output_dir / "selected_mods.final.json"
        final_selected.write_text(current.model_dump_json(indent=2), encoding="utf-8")
        status = "needs_manual_review" if attempts else "failed"
        report = AutonomousBuildReport(
            name=current.name,
            status=status,
            summary="Autonomous build stopped before launcher/runtime stability was proven.",
            attempts=attempts,
            final_selected_mods_path=str(final_selected),
            final_instance_path=final_instance_path,
            final_pack_artifact_path=final_pack_artifact,
            output_dir=str(output_dir),
            final_status_reason="runtime_proof_missing",
            runtime_proof_required=True,
            runtime_proof_observed=bool(attempts and attempts[-1].runtime_smoke_test_report and attempts[-1].runtime_smoke_test_report.runtime_proof_observed),
            smoke_test_mod_used=bool(attempts and attempts[-1].runtime_smoke_test_report and attempts[-1].runtime_smoke_test_report.smoke_test_mod_injected),
            stability_seconds_proven=attempts[-1].runtime_smoke_test_report.stability_seconds_proven if attempts and attempts[-1].runtime_smoke_test_report else 0,
            manual_required_reason="Runtime smoke-test proof markers were not observed.",
            user_next_steps=[
                "Complete launcher import/setup if required.",
                "Run launch-check with --launcher prism --instance-path <path> --wait-seconds 120 --inject-smoke-test-mod --validation-world until smoke-test markers prove PLAYER_JOINED_WORLD and STABLE_60_SECONDS.",
            ],
        )
        _write_autonomous_build_report(report, output_dir)
        if all_removed:
            _write_removed_mods(all_removed, output_dir)
        return report

    async def validate_pack(
        self,
        pack_dir: Path,
        *,
        pack_name: str | None = None,
        instance_id: str | None = None,
        force_validation: bool = False,
        check_config_only: bool = False,
    ) -> ValidationReport:
        pack_dir = Path(pack_dir)
        logs = _collect_logs(pack_dir)
        crash_report = _latest_crash_report(pack_dir)
        log_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in logs)
        analysis = analyze_failure(log_text) if log_text.strip() else None
        settings = self.settings
        prism_path = _setting(settings, "resolved_prism_path", "prism_executable_path", "prism_path")
        prism_root = _setting(settings, "resolved_prism_root", "prism_instances_path", "prism_root")
        validation_enabled = force_validation or bool(getattr(settings, "validation_enabled", False))
        setup_issues = _validation_setup_issues(
            pack_dir=pack_dir,
            prism_path=Path(prism_path) if prism_path else None,
            prism_root=Path(prism_root) if prism_root else None,
            timeout_seconds=int(getattr(settings, "launch_timeout_seconds", 300) or 0),
            validation_enabled=validation_enabled,
        )
        next_actions = _validation_setup_next_actions(setup_issues)
        if check_config_only:
            if setup_issues:
                return ValidationReport(
                    status="skipped",
                    validation_status="skipped",
                    launched=False,
                    details="Prism launch validation check skipped: " + "; ".join(setup_issues),
                    prism_executable_path=str(prism_path) if prism_path else None,
                    prism_instances_path=str(prism_root) if prism_root else None,
                    pack_path=str(pack_dir),
                    logs_collected=[str(path) for path in logs],
                    crash_report_path=str(crash_report) if crash_report else None,
                    crash_report_paths=[str(crash_report)] if crash_report else [],
                    latest_log_path=str(logs[-1]) if logs else None,
                    analysis=analysis,
                    likely_causes=[analysis.classification] if analysis else [],
                    suspected_failure_type=analysis.classification if analysis else None,
                    suggested_actions=next_actions,
                    next_actions=next_actions,
                    raw_summary=analysis.summary if analysis else "Configuration check skipped before launch.",
                )
            return ValidationReport(
                status="skipped",
                validation_status="skipped",
                launched=False,
                details="Prism launch validation configuration looks ready. No launch was attempted because --check-config-only was used.",
                prism_executable_path=str(prism_path),
                prism_instances_path=str(prism_root),
                pack_path=str(pack_dir),
                logs_collected=[str(path) for path in logs],
                crash_report_path=str(crash_report) if crash_report else None,
                crash_report_paths=[str(crash_report)] if crash_report else [],
                latest_log_path=str(logs[-1]) if logs else None,
                analysis=analysis,
                likely_causes=[analysis.classification] if analysis else [],
                suspected_failure_type=analysis.classification if analysis else None,
                next_actions=["run_validate_pack"],
                raw_summary=analysis.summary if analysis else "Configuration check passed.",
            )
        if setup_issues:
            return ValidationReport(
                status="skipped",
                validation_status="skipped",
                launched=False,
                details="Prism launch validation skipped: " + "; ".join(setup_issues),
                prism_executable_path=str(prism_path) if prism_path else None,
                prism_instances_path=str(prism_root) if prism_root else None,
                pack_path=str(pack_dir),
                logs_collected=[str(path) for path in logs],
                crash_report_path=str(crash_report) if crash_report else None,
                crash_report_paths=[str(crash_report)] if crash_report else [],
                latest_log_path=str(logs[-1]) if logs else None,
                analysis=analysis,
                likely_causes=[analysis.classification] if analysis else [],
                suspected_failure_type=analysis.classification if analysis else None,
                suggested_actions=analysis.repair_candidates if analysis else [],
                next_actions=next_actions,
                raw_summary=analysis.summary if analysis else "Validation skipped.",
            )
        resolved_instance_id = instance_id or safe_slug(pack_name or pack_dir.name, fallback="pack")
        try:
            validation = self.facade.validate_launch(resolved_instance_id)
        except Exception as exc:
            validation = ValidationReport(status="failed", launched=False, details=str(exc))
        merged_logs = list(dict.fromkeys(validation.logs_collected + [str(path) for path in logs]))
        if analysis and validation.analysis is None:
            validation.analysis = analysis
        validation.logs_collected = merged_logs
        validation.crash_report_path = validation.crash_report_path or (str(crash_report) if crash_report else None)
        validation.launched = validation.launched or validation.status in {"passed", "failed"}
        validation.likely_causes = validation.likely_causes or ([validation.analysis.classification] if validation.analysis else [])
        validation.suggested_actions = validation.suggested_actions or (validation.analysis.repair_candidates if validation.analysis else [])
        validation.raw_summary = validation.raw_summary or (validation.analysis.summary if validation.analysis else validation.details)
        validation.validation_status = validation.validation_status or validation.status
        validation.prism_executable_path = validation.prism_executable_path or str(prism_path)
        validation.prism_instances_path = validation.prism_instances_path or str(prism_root)
        validation.pack_path = validation.pack_path or str(pack_dir)
        validation.latest_log_path = validation.latest_log_path or (str(logs[-1]) if logs else None)
        validation.crash_report_paths = validation.crash_report_paths or ([str(crash_report)] if crash_report else [])
        validation.suspected_failure_type = validation.suspected_failure_type or (
            validation.analysis.classification if validation.analysis else None
        )
        return validation

    async def create_repair_plan(
        self,
        pack_dir: Path | None = None,
        *,
        report_path: Path | None = None,
    ) -> RepairReport:
        source_report_path = Path(report_path) if report_path else Path(pack_dir or ".") / "generation_report.json"
        report = AgentPackReport.model_validate_json(source_report_path.read_text(encoding="utf-8"))
        root = source_report_path.parent
        log_paths = [Path(path) for path in report.logs_collected if path]
        if report.launch_validation:
            log_paths.extend(Path(path) for path in report.launch_validation.logs_collected)
            if report.launch_validation.crash_report_path:
                log_paths.append(Path(report.launch_validation.crash_report_path))
        log_text = _read_existing_logs(log_paths)
        analysis = report.crash_analysis or (report.launch_validation.analysis if report.launch_validation else None)
        if log_text.strip():
            analysis = analyze_failure(log_text)
        classification = analysis.classification if analysis else "unknown"
        suspected = _suspected_mods(report, log_text)
        memory = self.memory.hints_for_mods(
            mods=suspected,
            minecraft_version=report.minecraft_version,
            loader=report.loader,
        )
        options = _repair_options_for(
            classification=classification,
            suspected_mods=suspected,
            log_text=log_text,
            memory_hints=memory,
        )
        repair = RepairReport(
            pack_name=report.name,
            source_report_path=str(source_report_path),
            validation_status=report.validation_status or "unknown",
            failed_stage=report.failed_stage or "validation_launch",
            crash_classification=classification,
            suspected_mods=suspected,
            repair_options=options,
            confidence=max([option.confidence for option in options], default=0.0),
            next_actions=_repair_next_actions(root, options),
            memory_advisories=memory["known_risk_matches"],
        )
        _write_repair_report(repair, root)
        write_cloud_ai_repair_prompt(root / "repair_report.json", output_dir=root)
        self.memory.record_repair_plan(
            pack_name=report.name,
            minecraft_version=report.minecraft_version,
            loader=report.loader,
            crash_classification=classification,
            suspected_mods=suspected,
            option_ids=[option.id for option in options],
        )
        return repair

    async def apply_repair_option(
        self,
        repair_report_path: Path,
        *,
        option_id: str,
        selected_mods_path: Path,
        output_path: Path,
    ) -> dict[str, Any]:
        repair = RepairReport.model_validate_json(Path(repair_report_path).read_text(encoding="utf-8"))
        selected = SelectedModList.model_validate_json(Path(selected_mods_path).read_text(encoding="utf-8"))
        option = next((item for item in repair.repair_options if item.id == option_id), None)
        if option is None:
            raise ValueError(f"repair option not found: {option_id}")
        updated, changes = _apply_repair_to_selected(selected, option)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
        self.memory.record_repair_applied(
            pack_name=selected.name,
            minecraft_version=selected.minecraft_version,
            loader=selected.loader,
            option_id=option.id,
            action_type=option.action_type,
            target_slug=option.target_slug,
        )
        return {
            "changed": bool(changes),
            "changes": changes,
            "output_path": str(output_path),
            "selected_mods": updated,
        }

    async def _inspect_hit(self, hit: dict[str, Any], *, loader: str, minecraft_version: str) -> dict[str, Any]:
        project_id = hit.get("project_id") or hit.get("id") or hit.get("slug")
        from mythweaver.catalog.content_kinds import content_kind_from_modrinth_project_type, modrinth_version_uses_loader_filter

        k, _ = content_kind_from_modrinth_project_type(hit.get("project_type"))
        versions = await self._versions_for(hit, str(project_id), loader=loader, minecraft_version=minecraft_version, content_kind=k)
        if not versions and minecraft_version != "auto":
            versions = await self._versions_for(hit, str(project_id), loader=loader, minecraft_version="auto", content_kind=k)
        if not versions and str(hit.get("project_type", "")).strip().lower() == "mod" and k == "mod":
            versions = await self._versions_for(
                hit, str(project_id), loader=loader, minecraft_version=minecraft_version, content_kind="datapack"
            )
            if not versions and minecraft_version != "auto":
                versions = await self._versions_for(
                    hit, str(project_id), loader=loader, minecraft_version="auto", content_kind="datapack"
                )
        require_loader = modrinth_version_uses_loader_filter(k)
        details = _installability_details(
            hit, versions, loader=loader, minecraft_version=minecraft_version, require_loader_match=require_loader
        )
        compatible = []
        candidate = details["candidate"]
        if candidate and details["selected_version"]:
            compatible.append(details["selected_version"])
        capabilities = set(infer_candidate_capabilities(candidate)) if candidate else _capabilities_from_hit(hit)
        warnings = []
        if not compatible:
            warnings.append(details["installability_message"])
        return {
            "name": hit.get("title", project_id),
            "slug": hit.get("slug", project_id),
            "project_id": project_id,
            "summary": hit.get("description", ""),
            "downloads": hit.get("downloads", 0),
            "followers": hit.get("followers", hit.get("follows", 0)),
            "categories": hit.get("categories", []),
            "loaders": hit.get("loaders", []),
            "game_versions": hit.get("versions", []),
            "side_support": {"client": hit.get("client_side", "unknown"), "server": hit.get("server_side", "unknown")},
            "compatible_versions": [_version_summary(version) for version in compatible],
            "latest_compatible_version": _version_summary(compatible[0]) if compatible else None,
            "dependencies": _version_summary(compatible[0])["dependencies"] if compatible else [],
            "files": _version_summary(compatible[0])["files"] if compatible else [],
            "installable": bool(compatible),
            "installable_for_requested_target": details["installable_for_requested_target"],
            "installability_status": "installable" if compatible else "not_installable",
            "installability_reason": details["installability_reason"],
            "installability_message": details["installability_message"],
            "compatible_versions_found": len(compatible),
            "selected_compatible_version": _version_summary(compatible[0]) if compatible else None,
            "loader_compatibility": details["loader_compatibility"],
            "minecraft_version_compatibility": details["minecraft_version_compatibility"],
            "installable_file_availability": details["installable_file_availability"],
            "project_status": details["project_status"],
            "version_status": details["version_status"],
            "capabilities": sorted(capabilities),
            "probable_role": _probable_role(capabilities),
            "fit_notes": _fit_notes(candidate, capabilities) if candidate else warnings,
            "warnings": warnings,
            "dependency_count": len(compatible[0].get("dependencies", [])) if compatible else 0,
            "micro_or_novelty": bool(candidate and is_novelty_candidate(candidate)),
            "source_links": {
                "modrinth": f"https://modrinth.com/mod/{hit.get('slug', project_id)}",
                "source": hit.get("source_url"),
                "issues": hit.get("issues_url"),
                "wiki": hit.get("wiki_url"),
            },
        }

    async def _versions_for(
        self,
        hit: dict[str, Any],
        identifier: str,
        *,
        loader: str,
        minecraft_version: str,
        content_kind: str = "mod",
    ) -> list[dict[str, Any]]:
        from mythweaver.catalog.content_kinds import modrinth_version_uses_loader_filter

        use_loader_filter = modrinth_version_uses_loader_filter(content_kind)  # type: ignore[arg-type]
        identifiers = list(dict.fromkeys([identifier, hit.get("slug"), hit.get("id")]))
        for current in identifiers:
            if not current:
                continue
            versions = await self.facade.modrinth.list_project_versions(
                current,
                loader=loader,
                minecraft_version=minecraft_version,
                include_changelog=False,
                use_loader_filter=use_loader_filter,
            )
            if versions:
                return versions
        return []

    async def _hydrate_selected_mods(self, selected: SelectedModList) -> tuple[list[CandidateMod], list[RejectedMod]]:
        from mythweaver.catalog.cf_candidate_builder import candidate_mod_from_curseforge
        from mythweaver.catalog.content_kinds import (
            content_kind_from_curseforge_class_id,
            content_kind_from_modrinth_project_type,
            modrinth_version_uses_loader_filter,
        )
        from mythweaver.catalog.selection_normalize import normalized_selection_rows
        from mythweaver.sources.curseforge import CurseForgeSourceProvider

        candidates: list[CandidateMod] = []
        rejected: list[RejectedMod] = []
        seen_selected_keys: set[str] = set()
        seen_project_ids: set[str] = set()

        for row in normalized_selection_rows(selected):
            ident_key = f"{row.source}:{row.ref}".strip().lower()
            if ident_key in seen_selected_keys:
                rejected.append(
                    RejectedMod(
                        project_id=row.ref,
                        reason="duplicate_selected_entry",
                        detail="Duplicate slug or id in selected_mods.json / content list",
                    )
                )
                continue

            if row.source == "curseforge":
                cf = CurseForgeSourceProvider()
                if not cf.is_configured():
                    rejected.append(
                        RejectedMod(
                            project_id=row.ref,
                            reason="curseforge_not_configured",
                            detail="CURSEFORGE_API_KEY is not set; cannot resolve CurseForge selection rows.",
                        )
                    )
                    continue
                picked = await cf.pick_mod_and_file(
                    row.ref,
                    minecraft_version=selected.minecraft_version,
                    loader=selected.loader,
                    require_loader_match=row.kind == "mod",
                )
                if not picked:
                    if row.required:
                        rejected.append(
                            RejectedMod(
                                project_id=row.ref,
                                reason="no_compatible_installable_version",
                                detail="No CurseForge file matched the requested Minecraft version (and loader policy).",
                            )
                        )
                    else:
                        rejected.append(
                            RejectedMod(
                                project_id=row.ref,
                                reason="optional_not_resolved",
                                detail="Optional CurseForge row could not be resolved.",
                            )
                        )
                    continue
                mod, file_obj = picked
                class_id = mod.get("classId")
                inferred = content_kind_from_curseforge_class_id(int(class_id)) if class_id is not None else None
                if inferred is not None and inferred != row.kind:
                    rejected.append(
                        RejectedMod(
                            project_id=row.ref,
                            title=mod.get("name"),
                            reason="source_kind_mismatch",
                            detail=f"expected kind {row.kind} but CurseForge classId maps to {inferred}",
                        )
                    )
                    continue
                try:
                    candidate = candidate_mod_from_curseforge(
                        mod,
                        file_obj,
                        content_kind=row.kind,
                        content_placement=row.placement,
                        platform_class_id=int(class_id) if class_id is not None else None,
                        selection_type=_selection_type_from_normalized(row),
                        why_selected=[row.reason_selected] if row.reason_selected else list(row.notes),
                    )
                except Exception as exc:
                    rejected.append(
                        RejectedMod(
                            project_id=row.ref,
                            title=mod.get("name"),
                            reason="invalid_metadata",
                            detail=str(exc),
                        )
                    )
                    continue
                candidate.enabled_by_default = row.enabled_by_default
                candidate.matched_capabilities = sorted(infer_candidate_capabilities(candidate))
                pid_norm = str(mod.get("id") or "").strip().lower()
                if pid_norm and pid_norm in seen_project_ids:
                    rejected.append(
                        RejectedMod(
                            project_id=row.ref,
                            title=mod.get("name"),
                            reason="duplicate_selected_modrinth_project",
                            detail="Same project already selected under another entry",
                        )
                    )
                    continue
                candidates.append(candidate)
                seen_selected_keys.add(ident_key)
                if pid_norm:
                    seen_project_ids.add(pid_norm)
                continue

            try:
                project = await self.facade.modrinth.get_project(row.ref)
            except Exception:
                if row.required:
                    rejected.append(RejectedMod(project_id=row.ref, reason="project_not_found"))
                else:
                    rejected.append(
                        RejectedMod(project_id=row.ref, reason="optional_not_resolved", detail="Optional Modrinth row was not found.")
                    )
                continue
            pid_norm = str(project.get("id") or project.get("project_id") or "").strip().lower()
            if pid_norm and pid_norm in seen_project_ids:
                rejected.append(
                    RejectedMod(
                        project_id=row.ref,
                        title=project.get("title"),
                        reason="duplicate_selected_modrinth_project",
                        detail="Same Modrinth project already selected under another entry",
                    )
                )
                continue
            platform_kind, _ = content_kind_from_modrinth_project_type(project.get("project_type"))
            if platform_kind != row.kind:
                if not (
                    str(project.get("project_type", "")).strip().lower() == "mod"
                    and row.kind == "datapack"
                ):
                    rejected.append(
                        RejectedMod(
                            project_id=row.ref,
                            title=project.get("title"),
                            reason="source_kind_mismatch",
                            detail=f"expected kind {row.kind} but Modrinth project_type resolves to {platform_kind}",
                        )
                    )
                    continue
            if project.get("status") in {"archived", "unlisted", "rejected", "withheld"}:
                rejected.append(RejectedMod(project_id=row.ref, title=project.get("title"), reason="project_not_installable"))
                continue
            require_loader = modrinth_version_uses_loader_filter(row.kind)
            versions = await self._versions_for(
                project, row.ref, loader=selected.loader, minecraft_version=selected.minecraft_version, content_kind=row.kind
            )
            if not versions and selected.minecraft_version != "auto":
                versions = await self._versions_for(
                    project, row.ref, loader=selected.loader, minecraft_version="auto", content_kind=row.kind
                )
            if (
                not versions
                and str(project.get("project_type", "")).strip().lower() == "mod"
                and row.kind == "mod"
            ):
                versions = await self._versions_for(
                    project,
                    row.ref,
                    loader=selected.loader,
                    minecraft_version=selected.minecraft_version,
                    content_kind="datapack",
                )
                if not versions and selected.minecraft_version != "auto":
                    versions = await self._versions_for(
                        project,
                        row.ref,
                        loader=selected.loader,
                        minecraft_version="auto",
                        content_kind="datapack",
                    )
            details = _installability_details(
                project,
                versions,
                loader=selected.loader,
                minecraft_version=selected.minecraft_version,
                require_loader_match=require_loader,
            )
            candidate = details["candidate"]
            if not candidate:
                if row.required:
                    rejected.append(
                        RejectedMod(
                            project_id=row.ref,
                            title=project.get("title"),
                            reason="no_compatible_installable_version",
                            detail=f"{details['installability_reason']}: {details['installability_message']}",
                        )
                    )
                else:
                    rejected.append(
                        RejectedMod(
                            project_id=row.ref,
                            title=project.get("title"),
                            reason="optional_not_resolved",
                            detail=f"{details['installability_reason']}: {details['installability_message']}",
                        )
                    )
                continue
            sel_ver = details["selected_version"]
            if (
                row.kind == "datapack"
                and str(project.get("project_type", "")).strip().lower() == "mod"
                and sel_ver is not None
                and not modrinth_version_loaders_effectively_datapack_only(sel_ver)
            ):
                rejected.append(
                    RejectedMod(
                        project_id=row.ref,
                        title=project.get("title"),
                        reason="source_kind_mismatch",
                        detail="Modrinth project_type is mod but the resolved version is not datapack-only; row kind datapack is inconsistent.",
                    )
                )
                continue
            candidate = apply_modrinth_mod_datapack_edge_to_candidate(candidate, sel_ver or {})
            edge_on = modrinth_mod_project_datapack_edge_applies(
                project_type=project.get("project_type"), version=sel_ver or {}
            )
            if edge_on:
                candidate = candidate.model_copy(update={"enabled_by_default": row.enabled_by_default})
            else:
                candidate = candidate.model_copy(
                    update={
                        "content_kind": row.kind,
                        "content_placement": row.placement,
                        "enabled_by_default": row.enabled_by_default,
                    }
                )
            sel_notes = [row.reason_selected] if row.reason_selected else list(row.notes)
            merged_why: list[str] = list(sel_notes)
            for w in candidate.why_selected:
                if w not in merged_why:
                    merged_why.append(w)
            candidate = candidate.model_copy(update={"why_selected": merged_why})
            candidate.selection_type = _selection_type_from_normalized(row)
            candidate.matched_capabilities = sorted(infer_candidate_capabilities(candidate))
            candidates.append(candidate)
            seen_selected_keys.add(ident_key)
            if pid_norm:
                seen_project_ids.add(pid_norm)
        return candidates, rejected

    def _report(self, selected: SelectedModList, **updates: Any) -> AgentPackReport:
        base = {
            "run_id": str(uuid.uuid4()),
            "status": "completed",
            "name": selected.name,
            "summary": selected.summary,
            "minecraft_version": selected.minecraft_version,
            "loader": selected.loader,
            "next_actions": ["build_from_list"],
        }
        base.update(updates)
        if "removed_mods" not in base:
            rejected = list(base.get("rejected_mods", []))
            rejected.extend(base.get("unresolved_mods", []))
            rejected.extend(base.get("incompatible_mods", []))
            base["removed_mods"] = _removed_mods_from_rejections(selected, rejected)
        if base["status"] == "failed" and not base.get("next_actions"):
            base["next_actions"] = ["replace_or_remove_rejected_mods", "rerun_verify_list"]
        return AgentPackReport.model_validate(base)


def _normalize_project_hit(hit: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(hit)
    normalized.setdefault("project_id", normalized.get("id") or normalized.get("slug"))
    normalized.setdefault("follows", normalized.get("followers", 0))
    normalized.setdefault("versions", normalized.get("game_versions", []))
    return normalized


def _first_candidate(
    hit: dict[str, Any],
    versions: list[dict[str, Any]],
    *,
    loader: str,
    minecraft_version: str,
    require_loader_match: bool = True,
) -> CandidateMod | None:
    return _installability_details(
        hit, versions, loader=loader, minecraft_version=minecraft_version, require_loader_match=require_loader_match
    )["candidate"]


def _installability_details(
    hit: dict[str, Any],
    versions: list[dict[str, Any]],
    *,
    loader: str,
    minecraft_version: str,
    require_loader_match: bool = True,
) -> dict[str, Any]:
    project_status = hit.get("status", "unknown")
    project_installable = project_status not in {"archived", "unlisted", "rejected", "withheld"}
    loader_compatibility = _loader_compatibility(hit, versions, loader, require_loader_match=require_loader_match)
    minecraft_version_compatibility = _minecraft_version_compatibility(hit, versions, minecraft_version)
    installable_file_availability = any(bool(version.get("files")) for version in versions)
    version_status = versions[0].get("status", "unknown") if versions else None
    invalid_metadata_reason: str | None = None

    relax_iters = [False]
    if require_loader_match and str(hit.get("project_type", "")).strip().lower() == "mod":
        relax_iters.append(True)
    for relax_mod_datapack_edge in relax_iters:
        for version in versions:
            if not modrinth_version_dict_installable(
                version,
                loader,
                minecraft_version,
                require_loader=require_loader_match,
                relax_mod_datapack_edge=relax_mod_datapack_edge,
            ):
                continue
            try:
                candidate = candidate_from_project_hit(_normalize_project_hit(hit), version)
                return {
                    "installable_for_requested_target": True,
                    "installability_reason": None,
                    "installability_message": "Installable for requested target.",
                    "candidate": candidate,
                    "selected_version": version,
                    "loader_compatibility": True,
                    "minecraft_version_compatibility": True,
                    "installable_file_availability": True,
                    "project_status": project_status,
                    "version_status": version.get("status", "unknown"),
                }
            except (KeyError, ValueError, ValidationError) as exc:
                invalid_metadata_reason = str(exc)

    reason = _installability_reason(
        versions=versions,
        project_installable=project_installable,
        loader_compatibility=loader_compatibility,
        minecraft_version_compatibility=minecraft_version_compatibility,
        installable_file_availability=installable_file_availability,
        invalid_metadata_reason=invalid_metadata_reason,
    )
    message = _installability_message(hit, loader, minecraft_version, reason, invalid_metadata_reason)
    return {
        "installable_for_requested_target": False,
        "installability_reason": reason,
        "installability_message": message,
        "candidate": None,
        "selected_version": None,
        "loader_compatibility": loader_compatibility,
        "minecraft_version_compatibility": minecraft_version_compatibility,
        "installable_file_availability": installable_file_availability,
        "project_status": project_status,
        "version_status": version_status,
    }


def _loader_compatibility(hit: dict[str, Any], versions: list[dict[str, Any]], loader: str, *, require_loader_match: bool = True) -> bool:
    if not require_loader_match:
        return True
    loader = loader.lower()
    if any(loader in [value.lower() for value in version.get("loaders", [])] for version in versions):
        return True
    if str(hit.get("project_type", "")).strip().lower() == "mod" and any(
        modrinth_version_loaders_effectively_datapack_only(v) for v in versions
    ):
        return True
    return loader in [value.lower() for value in hit.get("loaders", [])]


def _minecraft_version_compatibility(hit: dict[str, Any], versions: list[dict[str, Any]], minecraft_version: str) -> bool:
    if minecraft_version == "auto":
        return True
    target = minecraft_version.lower()
    if any(target in [value.lower() for value in version.get("game_versions", [])] for version in versions):
        return True
    return target in [value.lower() for value in hit.get("versions", [])]


def _installability_reason(
    *,
    versions: list[dict[str, Any]],
    project_installable: bool,
    loader_compatibility: bool,
    minecraft_version_compatibility: bool,
    installable_file_availability: bool,
    invalid_metadata_reason: str | None,
) -> str:
    if not project_installable:
        return "project_not_installable"
    if not versions:
        return "no_versions_found"
    if not loader_compatibility:
        return "loader_mismatch"
    if not minecraft_version_compatibility:
        return "minecraft_version_mismatch"
    if not any(version.get("status", "listed") in {"listed", "unlisted"} for version in versions):
        return "version_status_not_installable"
    if not installable_file_availability:
        return "missing_download_file"
    if invalid_metadata_reason:
        return "invalid_modrinth_metadata"
    return "no_compatible_installable_version"


def _installability_message(
    hit: dict[str, Any],
    loader: str,
    minecraft_version: str,
    reason: str,
    invalid_metadata_reason: str | None,
) -> str:
    loader_label = loader[:1].upper() + loader[1:]
    if reason in {"loader_mismatch", "minecraft_version_mismatch", "no_compatible_installable_version"}:
        return f"Project exists, but no installable {loader_label} {minecraft_version} version was found."
    if reason == "project_not_installable":
        return f"Project exists, but project status is {hit.get('status', 'unknown')}."
    if reason == "missing_download_file":
        return f"Project exists, but no installable file was found for {loader_label} {minecraft_version}."
    if reason == "invalid_modrinth_metadata":
        return f"Project exists, but compatible metadata is invalid: {invalid_metadata_reason}"
    if reason == "version_status_not_installable":
        return "Project exists, but compatible versions are not listed/installable."
    return f"Project exists, but no installable {loader_label} {minecraft_version} version was found."


def _profile_from_selected(selected: SelectedModList) -> RequirementProfile:
    keys: list[str] = [entry.slug or entry.modrinth_id or "" for entry in selected.mods]
    keys.extend(entry.slug for entry in selected.content)
    return RequirementProfile(
        name=selected.name,
        summary=selected.summary,
        loader=selected.loader,
        minecraft_version=selected.minecraft_version,
        search_keywords=keys,
    )


def _selection_type_from_normalized(row: Any) -> str:
    role = getattr(row, "role", "theme")
    if role == "dependency":
        return "dependency_added"
    if role in {"foundation", "shader_support"}:
        return "selected_foundation_mod"
    if role == "optional":
        return "optional_recommendation"
    return "selected_theme_mod"


def _selection_type(entry: SelectedModEntry) -> str:
    if entry.role == "dependency":
        return "dependency_added"
    if entry.role in {"foundation", "shader_support"}:
        return "selected_foundation_mod"
    if entry.role == "optional":
        return "optional_recommendation"
    return "selected_theme_mod"


def _version_summary(version: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": version.get("id"),
        "project_id": version.get("project_id"),
        "version_number": version.get("version_number"),
        "game_versions": version.get("game_versions", []),
        "loaders": version.get("loaders", []),
        "status": version.get("status"),
        "dependencies": version.get("dependencies", []),
        "files": [
            {
                "filename": file.get("filename"),
                "url": file.get("url"),
                "hashes": file.get("hashes", {}),
                "size": file.get("size", file.get("fileSize", 0)),
                "primary": file.get("primary", False),
            }
            for file in version.get("files", [])
        ],
    }


def _capabilities_from_hit(hit: dict[str, Any]) -> set[str]:
    text = _hit_text(hit)
    capabilities: set[str] = set()
    if "sodium" in text:
        capabilities.add("renderer_optimization")
    if "lithium" in text:
        capabilities.add("logic_optimization")
    if "ferrite" in text:
        capabilities.add("memory_optimization")
    if "iris" in text or "shader" in text:
        capabilities.add("shader_support")
    if "dungeon" in text:
        capabilities.update({"dungeons", "exploration", "structures"})
    return capabilities


def _probable_role(capabilities: set[str]) -> str:
    if capabilities & {"renderer_optimization", "logic_optimization", "memory_optimization", "entity_culling"}:
        return "foundation"
    if "shader_support" in capabilities:
        return "shader_support"
    if capabilities & {"waystones", "maps"}:
        return "utility"
    return "theme"


def _fit_notes(candidate: CandidateMod, capabilities: set[str]) -> list[str]:
    notes = [f"latest compatible version: {candidate.selected_version.version_number}"]
    if capabilities:
        notes.append("capabilities: " + ", ".join(sorted(capabilities)))
    if candidate.selected_version.dependencies:
        notes.append(f"dependencies: {len(candidate.selected_version.dependencies)}")
    return notes


def _hit_text(hit: dict[str, Any]) -> str:
    return " ".join(
        [
            str(hit.get("title", "")),
            str(hit.get("slug", "")),
            str(hit.get("description", "")),
            " ".join(hit.get("categories", [])),
        ]
    ).lower()


def _sort_index(sort: str) -> str:
    return {"updated": "updated", "downloads": "downloads", "follows": "follows"}.get(sort, "relevance")


PILLAR_TERMS = {
    "performance_foundation": [
        "sodium",
        "lithium",
        "ferrite",
        "modernfix",
        "immediatelyfast",
        "krypton",
        "entityculling",
        "optimization",
        "performance",
        "renderer",
        "memory",
    ],
    "worldgen": ["terralith", "tectonic", "regions unexplored", "biomes", "worldgen", "terrain"],
    "structures": ["structures", "dungeons", "towers", "villages", "strongholds", "mineshafts", "ruins", "yungs", "towns"],
    "exploration": ["compass", "map", "waystones", "dungeons", "adventure", "quests", "exploration"],
    "mobs_or_combat": ["mobs", "bosses", "combat", "weapons", "better combat", "simply swords", "adventurez"],
    "quality_of_life": ["modmenu", "jei", "emi", "jade", "appleskin", "mouse tweaks", "inventory", "utility", "config"],
    "atmosphere": ["sound", "visual", "ambience", "particles", "shader", "iris", "presence footsteps"],
    "navigation": ["xaero", "journeymap", "map", "minimap", "compass", "waystones"],
    "storage_or_inventory": ["storage", "backpacks", "inventory", "drawers", "chests"],
}

PILLAR_SEARCH_TERMS = {
    "performance_foundation": [
        "Fabric 1.20.1 performance optimization sodium lithium ferrite",
        "Fabric 1.20.1 entity culling optimization",
    ],
    "worldgen": ["Fabric 1.20.1 terrain worldgen biomes", "Fabric 1.20.1 maintained worldgen overhaul"],
    "structures": ["Fabric 1.20.1 medieval structures dungeons", "Fabric 1.20.1 village towers ruins"],
    "exploration": ["Fabric 1.20.1 exploration dungeons compass maps", "Fabric 1.20.1 adventure exploration utility"],
    "mobs_or_combat": ["Fabric 1.20.1 combat mobs bosses", "Fabric 1.20.1 weapons combat overhaul"],
    "quality_of_life": ["Fabric 1.20.1 QoL utility mod menu jade", "Fabric 1.20.1 inventory utility maintained"],
    "atmosphere": ["Fabric 1.20.1 atmosphere sounds particles shader", "Fabric 1.20.1 ambience visual effects"],
    "navigation": ["Fabric 1.20.1 minimap lightweight", "Fabric 1.20.1 world map Xaero alternative"],
    "storage_or_inventory": ["Fabric 1.20.1 storage backpacks inventory", "Fabric 1.20.1 chests drawers storage"],
}


def _review_pillar_coverage(candidates: list[CandidateMod], design: PackDesign | None = None) -> list[PillarCoverage]:
    pillars: list[PillarCoverage] = []
    for pillar, terms in PILLAR_TERMS.items():
        matches = [candidate.slug for candidate in candidates if _candidate_matches_terms(candidate, terms)]
        status = "missing"
        if len(matches) == 1:
            status = "thin" if pillar in {"performance_foundation", "structures", "worldgen"} else "covered"
        elif 2 <= len(matches) <= _pillar_overload_threshold(pillar):
            status = "covered"
        elif len(matches) > _pillar_overload_threshold(pillar):
            status = "overloaded"
        if _pillar_overload_is_healthy(pillar, matches, design):
            status = "covered"
        pillars.append(
            PillarCoverage(
                pillar=pillar,
                status=status,
                matching_mods=matches,
                detail=f"{len(matches)} selected mods matched {pillar}." if matches else "No selected mods matched this pillar.",
                suggested_search_terms=PILLAR_SEARCH_TERMS.get(pillar, []),
            )
        )
    return pillars


def _pillar_overload_threshold(pillar: str) -> int:
    return {"worldgen": 3, "structures": 5, "navigation": 3}.get(pillar, 4)


def _pillar_overload_is_healthy(pillar: str, matches: list[str], design: PackDesign | None) -> bool:
    if not design or design.archetype not in {"cozy_farming", "building_creative", "exploration_survival"}:
        return False
    if pillar == "performance_foundation":
        common = {"sodium", "lithium", "ferrite-core", "modernfix", "immediatelyfast", "entityculling", "ferritecore"}
        return 4 <= len(set(matches) & common) <= 8
    if pillar in {"quality_of_life", "atmosphere", "navigation", "storage_or_inventory"}:
        return True
    if pillar in {"worldgen", "structures", "exploration"}:
        return set(matches) <= {
            "terralith",
            "regions-unexplored",
            "ct-overhaul-village",
            "choicetheorems-overhauled-village",
            "explorify",
            "xaeros-minimap",
            "xaeros-world-map",
            "waystones",
            "travelersbackpack",
            "naturalist",
            "sound-physics-remastered",
        }
    return False


def _candidate_matches_terms(candidate: CandidateMod, terms: list[str]) -> bool:
    text = _review_text(candidate)
    capabilities = set(candidate.matched_capabilities or infer_candidate_capabilities(candidate))
    if any(term in text for term in terms):
        return True
    capability_aliases = {
        "performance_foundation": {"renderer_optimization", "logic_optimization", "memory_optimization", "entity_culling"},
        "structures": {"structures", "dungeons", "ruins"},
        "worldgen": {"forest_worldgen", "desert_worldgen", "volcanic_worldgen"},
        "exploration": {"exploration", "dungeons", "waystones", "maps"},
        "atmosphere": {"atmosphere", "ambient_sounds", "shader_support"},
    }
    return any(capabilities & aliases for key, aliases in capability_aliases.items() if any(term in PILLAR_TERMS[key] for term in terms))


def _review_duplicate_systems(candidates: list[CandidateMod], minecraft_version: str) -> list[ReviewIssue]:
    groups = {
        "duplicate_minimap": ["xaeros-minimap", "journeymap", "voxelmap"],
        "duplicate_world_map": ["xaeros-world-map", "journeymap"],
        "duplicate_shader_loader": ["iris", "oculus"],
        "duplicate_renderer_replacement": ["sodium", "embeddium", "rubidium", "canvas"],
        "duplicate_worldgen_overhaul": ["terralith", "tectonic", "biomes-o-plenty", "regions-unexplored", "oh-the-biomes-weve-gone"],
        "duplicate_combat_overhaul": ["better-combat", "epic-fight"],
        "duplicate_inventory_viewer": ["jei", "emi", "rei"],
    }
    by_slug = {candidate.slug: candidate for candidate in candidates}
    issues: list[ReviewIssue] = []
    for category, slugs in groups.items():
        matches = [slug for slug in slugs if slug in by_slug]
        if category in {"duplicate_minimap", "duplicate_world_map"} and set(matches) <= {"xaeros-minimap", "xaeros-world-map"}:
            continue
        if len(matches) > 1:
            severity = "high" if category in {"duplicate_shader_loader", "duplicate_renderer_replacement"} else "warning"
            if category == "duplicate_worldgen_overhaul" and len(matches) >= 3:
                severity = "high"
            issues.append(
                ReviewIssue(
                    severity=severity,
                    category=category,
                    title="Potential duplicate system",
                    detail=f"Multiple mods appear to cover the same system: {', '.join(matches)}.",
                    affected_mods=matches,
                    suggested_action="Keep the best-maintained compatible option and remove overlaps.",
                    replacement_search_terms=[
                        f"Fabric {minecraft_version} {category.replace('duplicate_', '').replace('_', ' ')} lightweight",
                    ],
                )
            )
    structure_like = [candidate.slug for candidate in candidates if _is_true_structure_mod(candidate)]
    if len(structure_like) > 5:
        issues.append(
            ReviewIssue(
                severity="warning",
                category="structure_overstack",
                title="Many large structure mods selected",
                affected_mods=structure_like,
                suggested_action="Review structure generation overlap before build.",
                replacement_search_terms=[f"Fabric {minecraft_version} balanced structure modpack structures"],
            )
        )
    return issues


def _is_true_structure_mod(candidate: CandidateMod) -> bool:
    slug = candidate.slug
    if slug in {
        "ct-overhaul-village",
        "choicetheorems-overhauled-village",
        "ctov",
        "explorify",
        "when-dungeons-arise",
    }:
        return True
    if slug in {
        "terralith",
        "regions-unexplored",
        "xaeros-minimap",
        "xaeros-world-map",
        "journeymap",
        "voxelmap",
        "waystones",
        "travelersbackpack",
        "naturalist",
        "toms-storage",
    }:
        return False
    text = _review_text(candidate)
    if any(term in text for term in ("minimap", "world map", "waystone", "backpack", "animal", "wildlife", "terrain", "biome")):
        return False
    return any(term in text for term in ("structure", "village", "dungeon", "tower", "ruin", "yung"))


def _review_memory_risks(memory_hints: dict[str, Any]) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    seen: set[tuple[str, ...]] = set()
    for entry in memory_hints.get("known_risk_matches", []):
        mods = list(entry.get("mods", []))
        key = tuple(sorted(mods + [entry.get("classification", "")]))
        if key in seen:
            continue
        seen.add(key)
        classification = entry.get("classification", "previous_failure")
        source = entry.get("source", "compatibility_memory")
        issues.append(
            ReviewIssue(
                severity="high",
                category="compatibility_memory",
                title="Known risky combination from local memory",
                detail=f"{classification} from {source}.",
                affected_mods=mods,
                suggested_action="Replace one mod or manually verify this combination before build.",
                replacement_search_terms=[f"Fabric compatible replacement for {' '.join(mods)}"],
            )
        )
    return issues


def _review_stale_low_signal(candidates: list[CandidateMod], minecraft_version: str) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    stale_cutoff = datetime.now(UTC) - timedelta(days=365 * 2)
    for candidate in candidates:
        if candidate.downloads < 1000:
            issues.append(
                ReviewIssue(
                    severity="warning",
                    category="low_signal_mod",
                    title="Low download signal",
                    detail=f"{candidate.title} has {candidate.downloads} downloads in Modrinth metadata.",
                    affected_mods=[candidate.slug],
                    suggested_action="Check whether this mod is intentional before build.",
                    replacement_search_terms=[f"Fabric {minecraft_version} maintained alternative for {candidate.slug}"],
                )
            )
        published = _parse_datetime(candidate.updated or candidate.selected_version.date_published)
        if published and published < stale_cutoff:
            issues.append(
                ReviewIssue(
                    severity="warning",
                    category="stale_mod",
                    title="Mod metadata looks stale",
                    detail=f"{candidate.title} was last updated/published around {published.date().isoformat()}.",
                    affected_mods=[candidate.slug],
                    suggested_action="Prefer a maintained alternative unless this mod is known stable.",
                    replacement_search_terms=[f"Fabric {minecraft_version} modern replacement for {candidate.slug}"],
                )
            )
        if candidate.selected_version.status in {"archived", "draft", "scheduled", "unknown"}:
            issues.append(
                ReviewIssue(
                    severity="high",
                    category="version_status",
                    title="Selected version status is risky",
                    detail=f"Version status: {candidate.selected_version.status}.",
                    affected_mods=[candidate.slug],
                    suggested_action="Use a listed compatible version or replace the mod.",
                    replacement_search_terms=[f"Fabric {minecraft_version} replacement for {candidate.slug}"],
                )
            )
    return issues


def _review_novelty_off_theme(candidates: list[CandidateMod], selected: SelectedModList) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    intent = " ".join(
        [selected.summary or "", selected.notes or ""]
        + [entry.reason_selected or "" for entry in selected.mods]
    ).lower()
    intent_terms = {term for term in intent.replace(",", " ").replace(".", " ").split() if len(term) >= 5}
    for candidate in candidates:
        text = _review_text(candidate)
        capabilities = set(candidate.matched_capabilities or infer_candidate_capabilities(candidate))
        weak_reason = not candidate.why_selected or len(" ".join(candidate.why_selected).strip()) < 5
        weak_theme = bool(intent_terms) and not any(term in text for term in intent_terms) and not capabilities
        if is_novelty_candidate(candidate) or weak_reason or weak_theme:
            issues.append(
                ReviewIssue(
                    severity="warning",
                    category="novelty_or_off_theme",
                    title="Mod may be novelty-only, tiny, or weakly justified",
                    detail="The selected mod has limited theme evidence or looks like a novelty/cosmetic pick.",
                    affected_mods=[candidate.slug],
                    suggested_action="Ask the agent/cloud AI to justify or replace this mod.",
                    replacement_search_terms=[f"{selected.loader.title()} {selected.minecraft_version} maintained thematic alternative for {candidate.slug}"],
                )
            )
    return issues


def _review_score(
    issues: list[ReviewIssue],
    pillars: list[PillarCoverage],
    dependency_impact: DependencyImpactReport,
) -> int:
    score = 100
    penalties = {"critical": 30, "high": 15, "warning": 6, "info": 0}
    for issue in issues:
        score -= penalties[issue.severity]
    if any(pillar.pillar == "performance_foundation" and pillar.status == "missing" for pillar in pillars):
        score -= 15
    if dependency_impact.missing_dependencies:
        score -= 20
    return max(0, min(100, score))


def _review_recommendation(score: int, issues: list[ReviewIssue]) -> str:
    hard_blockers = [issue for issue in issues if _review_issue_blocks_build(issue)]
    severities = {issue.severity for issue in issues}
    if hard_blockers:
        return "do_not_build"
    if score >= 80 and "critical" not in severities:
        return "build"
    return "revise_first"


def _review_issue_blocks_build(issue: ReviewIssue) -> bool:
    if issue.severity == "critical":
        return True
    if issue.category in {"installability", "dependency_impact"} and issue.severity in {"high", "critical"}:
        return True
    if issue.category in {"version_status", "compatibility_memory"} and issue.severity == "critical":
        return True
    if issue.category == "design_forbidden_system" and issue.severity == "critical":
        return True
    return False


def _review_verdict(recommendation: str) -> str:
    if recommendation == "build":
        return "Good list. Build is reasonable after normal verification."
    if recommendation == "revise_first":
        return "Promising list, but revise before build."
    return "Do not build yet. Installability or compatibility risks need fixing."


def _review_next_actions(recommendation: str, has_prompt: bool) -> list[str]:
    if recommendation == "build":
        return ["run_build_from_list"]
    actions = ["inspect_review_report", "revise_selected_mods", "rerun_review_list"]
    if has_prompt:
        actions.insert(1, "use_cloud_ai_review_prompt")
    return actions


def _agent_finding_from_issue(
    issue: ReviewIssue,
    *,
    kind: str | None = None,
    confidence: str = "medium",
) -> AgentCheckFinding:
    resolved_kind = kind or _agent_kind_for_issue(issue)
    return AgentCheckFinding(
        severity=issue.severity,
        kind=resolved_kind,
        title=issue.title,
        detail=issue.detail,
        affected_mods=issue.affected_mods,
        confidence=confidence,
        ai_instruction=_agent_instruction_for(resolved_kind, issue),
        suggested_search_terms=issue.replacement_search_terms,
    )


def _agent_kind_for_issue(issue: ReviewIssue) -> str:
    if issue.category in {"installability", "version_status"} or issue.severity == "critical":
        return "technical_blocker"
    if issue.category == "dependency_impact":
        return "dependency_issue"
    if issue.category == "compatibility_memory":
        return "compatibility_risk"
    if issue.category == "pillar_coverage" and "performance" in issue.title.lower():
        return "performance_signal"
    if issue.category in {"low_signal_mod", "stale_mod"}:
        return "stale_or_low_signal"
    if "duplicate" in issue.category or "overstack" in issue.category or "overloaded" in issue.title.lower():
        return "possible_duplicate"
    if issue.category.startswith("design_") or issue.category in {"novelty_or_off_theme", "mod_role_discipline"}:
        return "theme_signal"
    return "ai_judgment_needed"


def _agent_kind_for_subjective(issue: ReviewIssue) -> str:
    if "duplicate" in issue.category or "overstack" in issue.category:
        return "possible_duplicate"
    if issue.category in {"low_signal_mod", "stale_mod"}:
        return "stale_or_low_signal"
    if issue.category.startswith("design_") or issue.category in {"novelty_or_off_theme", "mod_role_discipline"}:
        return "theme_signal"
    return "ai_judgment_needed"


def _agent_instruction_for(kind: str, issue: ReviewIssue) -> str:
    if kind in {"technical_blocker", "dependency_issue"}:
        return "Must fix before build/export: replace, remove, or resolve the affected mod."
    if kind == "compatibility_risk":
        return "Treat as a technical caution. Replace only if the risk applies to this pack."
    if kind == "possible_duplicate":
        return "Use creative judgment. Keep complementary mods even if they appear similar."
    if kind == "theme_signal":
        return "Use creative judgment against the user's theme and explicit anti-goals."
    if kind == "performance_signal":
        return "Consider performance support, especially for larger packs, but do not treat as a creative veto."
    if kind == "stale_or_low_signal":
        return "Check maintenance and popularity. Replace only if a better maintained equivalent fits the theme."
    return "Use AI judgment; MythWeaver is reporting a signal, not making the creative decision."


def _dedupe_findings(findings: list[AgentCheckFinding]) -> list[AgentCheckFinding]:
    deduped: list[AgentCheckFinding] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for finding in findings:
        key = (finding.kind, finding.title, tuple(sorted(finding.affected_mods)))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def _agent_check_summary(
    build_permission: str,
    hard_blockers: list[AgentCheckFinding],
    warnings: list[AgentCheckFinding],
    ai_judgment_needed: list[AgentCheckFinding],
) -> str:
    if build_permission == "blocked":
        return f"Blocked by {len(hard_blockers)} hard technical blocker(s). Fix those before build/export."
    if build_permission == "allowed_with_warnings":
        return f"No hard blockers. {len(warnings)} warning(s) and {len(ai_judgment_needed)} creative judgment signal(s) should be reviewed by the AI designer."
    return "No hard blockers or notable warnings. Build/export is allowed."


def _agent_check_next_steps(build_permission: str) -> list[str]:
    if build_permission == "blocked":
        return ["fix_hard_blockers", "rerun_agent_check", "rerun_verify_list"]
    if build_permission == "allowed_with_warnings":
        return ["review_ai_judgment_needed", "optionally_revise_selected_mods", "run_build_from_list"]
    return ["run_build_from_list"]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _review_text(candidate: CandidateMod) -> str:
    return " ".join(
        [
            candidate.slug,
            candidate.title,
            candidate.description,
            candidate.body or "",
            " ".join(candidate.categories),
            " ".join(candidate.why_selected),
        ]
    ).lower()


def _unique(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _setting(settings: object, *names: str):
    for name in names:
        if settings is None:
            return None
        value = getattr(settings, name, None)
        if callable(value) and name.startswith("resolved_"):
            value = value()
        if value:
            return value
    return None


def _launcher_env_from_settings(settings: object) -> dict[str, str]:
    import os

    env = dict(os.environ)
    prism_path = _setting(settings, "resolved_prism_path", "prism_executable_path", "prism_path")
    prism_root = _setting(settings, "resolved_prism_root", "prism_instances_path", "prism_root")
    if prism_path:
        env["MYTHWEAVER_PRISM_EXECUTABLE_PATH"] = str(prism_path)
    if prism_root:
        env["MYTHWEAVER_PRISM_INSTANCES_PATH"] = str(prism_root)
    return env


def _validation_setup_issues(
    *,
    pack_dir: Path,
    prism_path: Path | None,
    prism_root: Path | None,
    timeout_seconds: int,
    validation_enabled: bool,
) -> list[str]:
    issues: list[str] = []
    if not pack_dir.exists():
        issues.append(f"generated pack folder does not exist: {pack_dir}")
    if not validation_enabled:
        issues.append("validation is disabled; set MYTHWEAVER_VALIDATION_ENABLED=true or pass --validation-enabled")
    if prism_path is None:
        issues.append("Prism executable path is not configured")
    elif not prism_path.exists():
        issues.append(f"Prism executable path does not exist: {prism_path}")
    elif not prism_path.is_file():
        issues.append(f"Prism executable path is not a file: {prism_path}")
    if prism_root is None:
        issues.append("Prism instances path is not configured")
    elif prism_root.exists() and not prism_root.is_dir():
        issues.append(f"Prism instances path is not a folder: {prism_root}")
    if timeout_seconds <= 0:
        issues.append("launch timeout must be a positive number of seconds")
    if pack_dir.exists() and not _has_pack_artifact(pack_dir):
        issues.append("generated pack folder does not contain a .mrpack or Prism instance files")
    return issues


def _has_pack_artifact(pack_dir: Path) -> bool:
    if any(pack_dir.glob("*.mrpack")):
        return True
    return (pack_dir / "instance.cfg").exists() or (pack_dir / ".minecraft").exists()


def _validation_setup_next_actions(issues: list[str]) -> list[str]:
    actions: list[str] = []
    text = " ".join(issues).lower()
    if "validation is disabled" in text:
        actions.append("Enable validation with --validation-enabled or MYTHWEAVER_VALIDATION_ENABLED=true.")
    if "prism executable" in text:
        actions.append("Set MYTHWEAVER_PRISM_EXECUTABLE_PATH or pass --prism-executable-path.")
    if "prism instances" in text:
        actions.append("Set MYTHWEAVER_PRISM_INSTANCES_PATH or pass --prism-instances-path.")
    if "pack folder" in text or ".mrpack" in text:
        actions.append("Build the pack first with build-from-list, then rerun validate-pack.")
    if "timeout" in text:
        actions.append("Set MYTHWEAVER_LAUNCH_TIMEOUT_SECONDS to a positive value.")
    return actions or ["Review Prism settings and rerun validate-pack --check-config-only."]


def _collect_logs(pack_dir: Path) -> list[Path]:
    candidates = []
    for pattern in (
        "**/latest.log",
        "**/crash-reports/*.txt",
        "**/launcher*.log",
        "**/prismlauncher*.log",
    ):
        candidates.extend(pack_dir.glob(pattern))
    return sorted({path for path in candidates if path.is_file()}, key=lambda path: str(path))


def _latest_crash_report(pack_dir: Path) -> Path | None:
    crashes = [path for path in pack_dir.glob("**/crash-reports/*.txt") if path.is_file()]
    if not crashes:
        return None
    return sorted(crashes, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def _memory_updates_for_validation(validation: ValidationReport) -> list[str]:
    if validation.status == "passed":
        return ["recorded_successful_pack"]
    if validation.status == "failed":
        return ["recorded_failed_pack"]
    return []


def _next_actions_after_validation(validation: ValidationReport) -> list[str]:
    if validation.status == "passed":
        return ["inspect_report", "share_or_archive_pack"]
    if validation.status == "failed":
        return ["inspect_logs", "replace_suspected_mods", "rerun_validate_pack"]
    return ["configure_prism_validation", "run_validate_pack"]


def _read_existing_logs(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in dict.fromkeys(paths):
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _suspected_mods(report: AgentPackReport, log_text: str) -> list[str]:
    suspects: list[str] = []
    if report.launch_validation:
        suspects.extend(report.launch_validation.suspected_mods)
    known = [mod.slug for mod in report.selected_mods + report.user_selected_mods + report.dependency_added_mods if mod.slug]
    lower = log_text.lower()
    for slug in known:
        if slug and slug.lower() in lower:
            suspects.append(slug)
    for pattern in (
        r"mod id[:\s'\"]+([a-z0-9_.-]+)",
        r"duplicate mod(?: id)?[:\s'\"]+([a-z0-9_.-]+)",
        r"requires dependency[:\s'\"]+([a-z0-9_.-]+)",
        r"requires ([a-z0-9_.-]+) to install",
        r"in ([a-z0-9_.-]+) renderer",
    ):
        import re

        suspects.extend(match.group(1).strip(" .'\"") for match in re.finditer(pattern, lower))
    return sorted({suspect for suspect in suspects if suspect and suspect not in {"dependency", "mod", "id"}})


def _repair_options_for(
    *,
    classification: str,
    suspected_mods: list[str],
    log_text: str,
    memory_hints: dict[str, Any],
) -> list[RepairOption]:
    options: list[RepairOption] = []
    next_id = 1

    def add(action_type: str, *, target: str | None, reason: str, confidence: float, risk: str, **extra: Any) -> None:
        nonlocal next_id
        options.append(
            RepairOption(
                id=f"repair_{next_id:03d}",
                action_type=action_type,
                target_slug=target,
                target_mod=target,
                reason=reason,
                confidence=confidence,
                risk_level=risk,
                requires_agent_review=True,
                **extra,
            )
        )
        next_id += 1

    primary = suspected_mods[0] if suspected_mods else None
    if classification == "missing_dependency":
        missing = _missing_dependency_slug(log_text) or primary
        add(
            "add_missing_dependency",
            target=missing,
            reason="Launch log reports a missing required dependency.",
            confidence=0.8,
            risk="low",
            expected_effect="Include the required support mod in the selected list.",
            tradeoffs=["Adds one dependency; Modrinth verification still runs before build."],
        )
    elif classification == "duplicate_mod":
        add(
            "remove_duplicate_system",
            target=primary,
            reason="Launch log reports duplicate mod IDs or duplicate files.",
            confidence=0.75,
            risk="medium",
            expected_effect="Remove the lower-confidence duplicate from the selected list.",
            tradeoffs=["Agent should confirm which duplicate is less important."],
        )
    elif classification in {"mixin_failure", "mod_initialization_failure"}:
        add(
            "remove_mod",
            target=primary,
            reason="Crash evidence points to a mod transform or initialization failure.",
            confidence=0.55,
            risk="high",
            expected_effect="Remove the suspected mod and rebuild to confirm.",
            tradeoffs=["May remove a user-selected feature; requires agent review."],
        )
        add(
            "replace_mod",
            target=primary,
            reason="A compatible replacement may preserve the same pack role with less risk.",
            confidence=0.45,
            risk="medium",
            replacement_query=_replacement_query(primary, classification),
            replacement_candidates=_known_good_replacements(memory_hints),
            expected_effect="Swap the suspected mod for a verified compatible alternative.",
            tradeoffs=["Replacement still needs Modrinth verification before build."],
        )
    elif classification == "java_mismatch":
        add(
            "mark_manual_review_required",
            target=None,
            reason="The failure points to Java/runtime configuration rather than a mod choice.",
            confidence=0.85,
            risk="low",
            expected_effect="Change Prism Java configuration and validate again.",
            tradeoffs=["No selected mods are changed."],
        )
    elif classification == "config_parse_error":
        add(
            "mark_manual_review_required",
            target=None,
            reason="A configuration file failed parsing; repair depends on whether MythWeaver generated it.",
            confidence=0.65,
            risk="medium",
            expected_effect="Review or regenerate the broken config.",
            tradeoffs=["No selected mods are changed automatically."],
        )
    elif classification == "renderer_shader_conflict":
        add(
            "switch_shader_support_off",
            target=primary or "iris",
            reason="Renderer or shader stack appears involved in the failure.",
            confidence=0.65,
            risk="medium",
            replacement_candidates=_known_good_replacements(memory_hints),
            expected_effect="Remove shader support temporarily to isolate renderer conflicts.",
            tradeoffs=["Visual shader support may be lost until a safer stack is chosen."],
        )
    elif classification == "out_of_memory":
        add(
            "mark_manual_review_required",
            target=None,
            reason="Out-of-memory failures should first be handled by increasing allocated memory.",
            confidence=0.8,
            risk="low",
            expected_effect="Adjust Prism memory settings before changing mods.",
            tradeoffs=["No selected mods are changed."],
        )
        add(
            "reduce_mod_count",
            target=None,
            reason="If memory cannot be increased, reduce the heaviest optional content.",
            confidence=0.35,
            risk="high",
            expected_effect="Lower memory pressure.",
            tradeoffs=["May reduce pack scope; agent should choose candidates manually."],
        )
    else:
        add(
            "mark_manual_review_required",
            target=primary,
            reason="Crash classification is unknown; a human/agent should inspect the full log.",
            confidence=0.3,
            risk="high",
            expected_effect="Avoid unsafe automatic repair.",
            tradeoffs=["Use a binary-search workflow if no clearer evidence appears."],
        )
    return options


def _missing_dependency_slug(log_text: str) -> str | None:
    import re

    lower = log_text.lower()
    for pattern in (r"requires dependency[:\s'\"]+([a-z0-9_.-]+)", r"requires ([a-z0-9_.-]+) to install"):
        match = re.search(pattern, lower)
        if match:
            value = match.group(1).strip(" .'\"")
            if value not in {"dependency", "mod"}:
                return value
    return None


def _replacement_query(target: str | None, classification: str) -> str:
    if target and target in {"iris", "sodium", "indium"}:
        return "Fabric 1.20.1 renderer optimization shader support alternative"
    if classification == "mixin_failure":
        return "Fabric 1.20.1 compatible replacement for crashing mod"
    return "Fabric 1.20.1 compatible mod replacement"


def _known_good_replacements(memory_hints: dict[str, Any]) -> list[dict[str, Any]]:
    replacements: list[dict[str, Any]] = []
    for entry in memory_hints.get("renderer_stack_success", []):
        for slug in entry.get("mods", []):
            replacements.append({"slug": slug, "reason": "Seen in local known-good renderer stack."})
    return replacements[:5]


def _repair_next_actions(root: Path, options: list[RepairOption]) -> list[str]:
    first = options[0].id if options else "<option-id>"
    actions = [
        f"Review {root / 'repair_report.md'}",
        f"python -m mythweaver.cli.main apply-repair {root / 'repair_report.json'} --option-id {first} --selected-mods selected_mods.json --output selected_mods.repaired.json",
        "python -m mythweaver.cli.main build-from-list selected_mods.repaired.json --validate-launch",
    ]
    if options and options[0].action_type == "mark_manual_review_required" and "Java" in options[0].reason:
        actions.insert(1, "Configure Prism to use the Java version required by the selected Minecraft version.")
    return actions


def _write_repair_report(repair: RepairReport, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "repair_report.json"
    md_path = root / "repair_report.md"
    json_path.write_text(repair.model_dump_json(indent=2), encoding="utf-8")
    lines = [
        f"# Repair Report: {repair.pack_name}",
        "",
        "## Repair Summary",
        f"- Pack name: {repair.pack_name}",
        f"- Failure type: {repair.crash_classification}",
        f"- Suspected mods: {', '.join(repair.suspected_mods) if repair.suspected_mods else 'none'}",
        f"- Confidence: {repair.confidence:.2f}",
        "",
        "## Repair Options",
    ]
    for option in repair.repair_options:
        lines.extend(
            [
                f"### {option.id}",
                f"- Action: {option.action_type}",
                f"- Target: {option.target_slug or 'none'}",
                f"- Reason: {option.reason}",
                f"- Confidence: {option.confidence:.2f}",
                f"- Risk: {option.risk_level}",
                f"- Tradeoffs: {'; '.join(option.tradeoffs) if option.tradeoffs else 'none'}",
                f"- Command: python -m mythweaver.cli.main apply-repair {json_path} --option-id {option.id} --selected-mods selected_mods.json --output selected_mods.repaired.json",
                "",
            ]
        )
    lines.extend(["## Next Steps", *[f"- {action}" for action in repair.next_actions]])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_review_report(report: SelectedModReviewReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "review_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _write_agent_check_report(report: AgentCheckReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "agent_check_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _write_source_search_report(reports: list[SourceSearchResult], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = [report.model_dump(mode="json") for report in reports]
    (output_dir / "source_search_report.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_source_inspect_report(candidate: Any, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = candidate.model_dump(mode="json") if hasattr(candidate, "model_dump") else candidate
    (output_dir / "source_inspect_report.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_source_resolve_report(report: SourceResolveReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "source_resolve_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _write_removed_mods(removed_mods: list[RemovedSelectedMod], output_dir: Path) -> None:
    path = Path(output_dir) / "removed_mods.json"
    if not removed_mods:
        if path.is_file():
            path.unlink()
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = [item.model_dump(mode="json") for item in removed_mods]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_crash_analysis_report(report: CrashAnalysisReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "crash_analysis_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _write_launch_validation_report(report: LaunchValidationReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "launch_validation_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _write_stabilization_outputs(
    report: StabilizationReport,
    output_dir: Path,
    removed_mods: list[RemovedSelectedMod],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stabilization_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    _write_removed_mods(removed_mods, output_dir)
    notes = [
        f"# Stabilization Notes: {report.name}",
        "",
        report.summary,
        "",
        "Dry-run is not playable proof. A pack is only stable after launch and world-join validation.",
        "",
        "## Attempts",
    ]
    for attempt in report.attempts:
        notes.extend(
            [
                f"- Attempt {attempt.attempt_number}: verify={attempt.verify_status}, dry_run={attempt.dry_run_status}, launch={attempt.launch_status}",
                *(f"  - {change}" for change in attempt.changes_made),
            ]
        )
    if removed_mods:
        notes.extend(["", "## Removed Mods"])
        notes.extend(f"- {item.slug_or_id}: {item.reason}" for item in removed_mods)
    (output_dir / "stabilization_notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")


def _write_autonomous_build_report(report: AutonomousBuildReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "autonomous_build_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _concept_name_for_autonomous(
    concept_path: Path,
    concept_text: str,
    selected: SelectedModList | None,
) -> str:
    if selected is not None:
        return selected.name
    for line in concept_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return concept_path.stem.replace("_", " ").replace("-", " ").title() or "Autonomous Pack"


def _split_source_ref(source_ref: str) -> tuple[str, str]:
    if ":" not in source_ref:
        return "modrinth", source_ref
    source, ref = source_ref.split(":", 1)
    normalized = source.strip().lower()
    if normalized in {"modrinth", "curseforge", "github", "planetminecraft", "local", "direct_url"}:
        return normalized, ref
    return "modrinth", source_ref


def _repair_selected_for_runtime_crash(
    selected: SelectedModList,
    crash: CrashAnalysisReport,
) -> tuple[SelectedModList, list[RemovedSelectedMod]]:
    targets = _safe_runtime_removal_targets(crash)
    if not targets:
        return selected, []
    updated = selected.model_copy(deep=True)
    kept: list[SelectedModEntry] = []
    removed: list[RemovedSelectedMod] = []
    for entry in updated.mods:
        identifier = _normalize_selected_identifier(entry.identifier())
        if identifier in targets:
            removed.append(
                RemovedSelectedMod(
                    slug_or_id=entry.identifier(),
                    title=entry.slug or entry.modrinth_id,
                    reason=f"runtime crash repair: {_crash_reason(crash)}",
                    original_role=entry.role,
                    category_impact=_runtime_category_impact(identifier),
                    replacement_search_terms=_runtime_replacement_terms(identifier, selected),
                )
            )
        else:
            kept.append(entry)
    if not removed:
        return selected, []
    updated.mods = kept
    changelog = list(updated.repair_changelog)
    changelog.append(
        {
            "action": "runtime_stabilization",
            "removed_mods": [item.slug_or_id for item in removed],
            "reason": crash.summary,
        }
    )
    updated.repair_changelog = changelog
    return updated, removed


def _safe_runtime_removal_targets(crash: CrashAnalysisReport) -> set[str]:
    suspects = {_normalize_selected_identifier(mod) for mod in _crash_suspects(crash)}
    targets: set[str] = set()
    if crash.crashing_mod_id == "hwg" or "hwg" in suspects:
        targets.update({"hwg", "azurelib"})
    if crash.crashing_mod_id == "inventoryprofilesnext" or "inventoryprofilesnext" in suspects:
        targets.update({"inventoryprofilesnext", "inventory-profiles-next", "libipn"})
        if "fabric-language-kotlin" in suspects:
            targets.add("fabric-language-kotlin")
    return targets


def _crash_suspects(crash: CrashAnalysisReport) -> list[str]:
    suspects: list[str] = []
    if crash.crashing_mod_id:
        suspects.append(crash.crashing_mod_id)
    for finding in crash.findings:
        suspects.extend(finding.suspected_mods)
        if finding.missing_mod_id:
            suspects.append(finding.missing_mod_id)
    return sorted({_normalize_selected_identifier(item) for item in suspects if item})


def _normalize_selected_identifier(value: str) -> str:
    lower = value.strip().lower()
    aliases = {
        "inventory-profiles-next": "inventoryprofilesnext",
        "inventory_profiles_next": "inventoryprofilesnext",
    }
    return aliases.get(lower, lower)


def _crash_reason(crash: CrashAnalysisReport) -> str:
    if crash.crashing_mod_id:
        return f"{crash.crashing_mod_id} caused {crash.repair_recommendation}"
    return crash.summary


def _runtime_category_impact(identifier: str) -> list[str]:
    if identifier == "hwg":
        return ["combat", "weapons"]
    if identifier in {"inventoryprofilesnext", "inventory-profiles-next", "libipn"}:
        return ["client_qol", "inventory_management"]
    if identifier == "azurelib":
        return ["library_dependency"]
    return ["runtime_stability"]


def _runtime_replacement_terms(identifier: str, selected: SelectedModList) -> list[str]:
    if identifier == "hwg":
        return [f"{selected.loader.title()} {selected.minecraft_version} gun combat weapon mod Modrinth"]
    if identifier in {"inventoryprofilesnext", "inventory-profiles-next", "libipn"}:
        return [f"{selected.loader.title()} {selected.minecraft_version} inventory qol maintained Modrinth"]
    return [f"{selected.loader.title()} {selected.minecraft_version} replacement for {identifier}"]


def _write_design_review_report(report: PackDesignReviewReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "design_review_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _apply_repair_to_selected(selected: SelectedModList, option: RepairOption) -> tuple[SelectedModList, list[str]]:
    updated = selected.model_copy(deep=True)
    mods = list(updated.mods)
    changes: list[str] = []
    target = option.target_slug or option.target_mod_id or option.target_mod
    if option.action_type in {"remove_mod", "remove_duplicate_system", "switch_shader_support_off"} and target:
        before = len(mods)
        mods = [mod for mod in mods if mod.slug != target and mod.modrinth_id != target]
        if len(mods) != before:
            changes.append(f"removed {target}")
    elif option.action_type == "replace_mod" and target:
        role = "theme"
        for mod in mods:
            if mod.slug == target or mod.modrinth_id == target:
                role = mod.role
                break
        mods = [mod for mod in mods if mod.slug != target and mod.modrinth_id != target]
        replacement_slug = _replacement_slug(option)
        if replacement_slug:
            mods.append(
                SelectedModEntry(
                    slug=replacement_slug,
                    role=role,
                    required=True,
                    reason_selected=f"Added by MythWeaver repair plan: {option.reason}",
                )
            )
            changes.append(f"replaced {target} with {replacement_slug}")
    elif option.action_type == "add_missing_dependency" and target:
        if not any(mod.slug == target or mod.modrinth_id == target for mod in mods):
            mods.append(
                SelectedModEntry(
                    slug=target,
                    role="dependency",
                    required=True,
                    reason_selected="Added by MythWeaver repair plan",
                )
            )
            changes.append(f"added dependency {target}")
    elif option.action_type == "disable_optional_mod" and target:
        for mod in mods:
            if mod.slug == target or mod.modrinth_id == target:
                mod.required = False
                changes.append(f"marked {target} optional")
    updated.mods = mods
    changelog = list(updated.repair_changelog)
    changelog.append(
        {
            "option_id": option.id,
            "action_type": option.action_type,
            "target_slug": option.target_slug,
            "reason": option.reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    updated.repair_changelog = changelog
    return updated, changes


def _replacement_slug(option: RepairOption) -> str | None:
    for candidate in option.replacement_candidates:
        slug = candidate.get("slug") or candidate.get("project_id") or candidate.get("modrinth_id")
        if slug:
            return str(slug)
    return None


def _write_agent_report(report: AgentPackReport, output_dir: Path) -> None:
    from mythweaver.validation.content_export_policy import (
        collect_content_export_warnings,
        content_sections_dict,
        jjthunder_guidance_lines,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "generation_report.json"
    md_path = output_dir / "generation_report.md"
    report.generated_artifacts.extend(
        [
            BuildArtifact(kind="generation-report-json", path=str(json_path)),
            BuildArtifact(kind="generation-report-md", path=str(md_path)),
        ]
    )
    report.artifacts = list(report.generated_artifacts)
    pack_like_mods = [*report.user_selected_mods, *report.dependency_added_mods]
    if report.selected_mods and not pack_like_mods:
        pack_like_mods = list(report.selected_mods)
    content_warnings = collect_content_export_warnings(pack_like_mods)
    jj_lines = jjthunder_guidance_lines(pack_like_mods)
    sections = content_sections_dict(
        ResolvedPack(
            name=report.name,
            minecraft_version=report.minecraft_version,
            loader=report.loader,
            selected_mods=pack_like_mods,
        )
    )
    report.content_sections = sections
    json_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        f"# {report.name}",
        "",
        f"Status: {report.status}",
        f"Minecraft: {report.minecraft_version}",
        "",
        "## Build Result",
        f"- Selected mods: {len(report.selected_mods)}",
        f"- Artifacts: {len(report.generated_artifacts)}",
        "",
        "## Final artifact validation",
        f"- Status: {report.final_artifact_validation_status or 'not_run'}",
        f"- Report: {report.final_artifact_validation_report_path or 'n/a'}",
        f"- Summary: {report.final_artifact_validation_summary or 'n/a'}",
        "",
        "## Launch Validation",
        f"- Status: {report.validation_status or 'not_run'}",
        f"- Logs collected: {len(report.logs_collected)}",
        "",
        "## Compatibility Memory",
        *([f"- {update}" for update in report.compatibility_memory_updates] or ["- No memory updates."]),
        "",
        "## Top Issues",
        *([f"- {warning}" for warning in report.compatibility_warnings] or ["- None."]),
        "",
        "## Content export warnings",
        *([f"- {warning}" for warning in content_warnings] or ["- None."]),
        "",
        "## JJThunder-style guidance",
        *([f"- {line}" for line in jj_lines] or ["- Not triggered."]),
        "",
        "## Mods",
        *[f"- {m.title} ({m.slug}) [{getattr(m, 'content_kind', 'mod')}]" for m in pack_like_mods if getattr(m, "content_kind", "mod") == "mod"],
        "",
        "## Datapacks",
        *[f"- {m.title} ({m.slug})" for m in pack_like_mods if getattr(m, "content_kind", "mod") == "datapack"],
        "",
        "## Resource packs",
        *[f"- {m.title} ({m.slug}) — not enabled by default" for m in pack_like_mods if getattr(m, "content_kind", "mod") == "resourcepack"],
        "",
        "## Shader packs",
        *[f"- {m.title} ({m.slug}) — optional; not enabled by default; Iris typically required on Fabric" for m in pack_like_mods if getattr(m, "content_kind", "mod") == "shaderpack"],
        "",
        "## Manual world-creation content",
        *[
            f"- {m.title} ({m.slug})"
            for m in pack_like_mods
            if getattr(m, "content_kind", "mod") == "datapack" and getattr(m, "content_placement", None) == "manual_world_creation"
        ],
        "",
        "## User Selected Mods",
        *[f"- {mod.title} ({mod.slug})" for mod in report.user_selected_mods],
        "",
        "## Dependency Added Mods",
        *[f"- {mod.title} ({mod.slug})" for mod in report.dependency_added_mods],
        "",
        "## Rejected Mods",
        *[f"- {mod.title or mod.project_id}: {mod.reason}" for mod in report.rejected_mods],
        "",
        "## Next Actions",
        *[f"- {action}" for action in report.next_actions],
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _blocking_review_report(output_dir: Path) -> str | None:
    path = Path(output_dir) / "review_report.json"
    if not path.is_file():
        return None
    try:
        report = SelectedModReviewReport.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if report.build_recommendation != "do_not_build":
        return None
    return f"Build/export blocked because {path} recommends do_not_build."


def _removed_mods_from_rejections(selected: SelectedModList, rejections: list[RejectedMod]) -> list[RemovedSelectedMod]:
    entries = {entry.identifier(): entry for entry in selected.mods}
    by_slug = {entry.slug: entry for entry in selected.mods if entry.slug}
    removed: list[RemovedSelectedMod] = []
    seen: set[tuple[str, str]] = set()
    for rejection in rejections:
        identifier = rejection.project_id
        entry = entries.get(identifier) or by_slug.get(identifier)
        reason = _removed_reason(rejection.reason)
        key = (identifier, reason)
        if key in seen:
            continue
        seen.add(key)
        removed.append(
            RemovedSelectedMod(
                slug_or_id=identifier,
                title=rejection.title,
                reason=reason,
                original_role=entry.role if entry else None,
                category_impact=_category_impact_for(entry),
                replacement_search_terms=[
                    f"{selected.loader.title()} {selected.minecraft_version} replacement for {identifier}",
                    f"{selected.loader.title()} {selected.minecraft_version} {identifier.replace('-', ' ')} alternative",
                ],
            )
        )
    return removed


def _removed_reason(reason: str) -> str:
    mapping = {
        "project_not_found": "invalid slug/project id",
        "not_a_mod_project": "invalid slug/project id",
        "project_not_installable": "unavailable mod",
        "no_compatible_installable_version": "unsupported loader/version",
        "optional_not_resolved": "optional row skipped",
        "source_kind_mismatch": "kind/source mismatch",
        "curseforge_not_configured": "curseforge api key missing",
        "invalid_metadata": "invalid metadata",
        "missing_dependency": "dependency conflict",
        "dependency_resolution": "dependency conflict",
    }
    if "dependency" in reason:
        return mapping.get(reason, "dependency conflict")
    return mapping.get(reason, reason or "unknown reason")


def _category_impact_for(entry: SelectedModEntry | None) -> list[str]:
    if entry is None:
        return []
    impact = [entry.role]
    reason = (entry.reason_selected or "").lower()
    impact.extend(
        token
        for token in (
            "performance_foundation",
            "client_qol",
            "inventory_management",
            "farming",
            "cooking",
            "animals",
            "villages",
            "worldgen",
            "decoration",
            "building_blocks",
            "storage_solution",
        )
        if token in reason
    )
    return list(dict.fromkeys(impact))
