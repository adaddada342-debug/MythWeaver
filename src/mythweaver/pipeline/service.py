from __future__ import annotations

import uuid
from pathlib import Path

from mythweaver.builders.paths import safe_slug
from mythweaver.pipeline.constraints import (
    apply_profile_constraints,
    candidate_exclusion_matches,
    candidate_forbidden_capability_matches,
    candidate_negative_matches,
    candidate_positive_evidence,
    capability_terms,
    infer_candidate_capabilities,
)
from mythweaver.pipeline.dependencies import expand_required_dependencies
from mythweaver.pipeline.discovery import discover_candidates
from mythweaver.pipeline.performance import build_performance_foundation_plan
from mythweaver.pipeline.profile import profile_from_prompt
from mythweaver.pipeline.reports import write_generation_reports
from mythweaver.pipeline.sanitizer import sanitize_candidates_for_profile
from mythweaver.pipeline.selection import is_novelty_candidate, select_candidates
from mythweaver.pipeline.strategy import build_search_strategy
from mythweaver.schemas.contracts import (
    CandidateMod,
    ConfidenceScores,
    GenerationReport,
    GenerationRequest,
    PerformanceFoundationReport,
    PipelineStageResult,
    RejectedMod,
    ResolvedPack,
    ShaderSupportReport,
    ValidationReport,
)


class GenerationPipeline:
    def __init__(self, facade: object) -> None:
        self.facade = facade

    async def generate(self, request: GenerationRequest) -> GenerationReport:
        profile = apply_profile_constraints(request.profile or profile_from_prompt(request.prompt or ""))
        strict_profile_mode = request.strict_profile_mode if request.strict_profile_mode is not None else request.profile is not None
        output_dir = Path(request.output_dir or Path("output") / "generated" / safe_slug(profile.name, fallback="pack"))
        foundation = build_performance_foundation_plan(profile)
        strategy = build_search_strategy(profile, limit=request.limit)
        max_before_dependencies = profile.max_selected_before_dependencies or request.max_mods
        max_before_dependencies = min(max_before_dependencies, request.max_mods)
        run_id = str(uuid.uuid4())
        stages: list[PipelineStageResult] = [
            PipelineStageResult(name="profile", status="completed", message="Profile ready."),
            PipelineStageResult(name="search_strategy", status="completed", metadata={"plans": len(strategy.search_plans)}),
        ]

        try:
            discovery = await discover_candidates(self.facade.modrinth, strategy)
        except Exception as exc:
            report = GenerationReport(
                run_id=run_id,
                status="failed",
                profile=profile,
                strict_profile_mode=strict_profile_mode,
                failed_stage="discovery_error",
                stages=stages
                + [PipelineStageResult(name="discovery", status="failed", message=str(exc))],
                search_plans=strategy.search_plans,
                performance_foundation=foundation,
                shader_support=_shader_support_report(foundation, []),
                shader_recommendations=foundation.shader_recommendations,
                confidence=_confidence_scores(status="failed", selected_mods=[], profile=profile),
                output_dir=str(output_dir),
                next_actions=_next_actions("failed", foundation, [], failed_stage="discovery_error"),
            )
            report.artifacts.extend(write_generation_reports(report, output_dir))
            return report
        if not discovery.candidates:
            report = GenerationReport(
                run_id=run_id,
                status="failed",
                profile=profile,
                strict_profile_mode=strict_profile_mode,
                minecraft_version=discovery.minecraft_version,
                failed_stage="discovery_empty",
                stages=stages + [PipelineStageResult(name="discovery", status="failed", message="No verified candidates found.")],
                search_plans=strategy.search_plans,
                rejected_mods=discovery.rejected,
                performance_foundation=foundation,
                shader_support=_shader_support_report(foundation, []),
                shader_recommendations=foundation.shader_recommendations,
                confidence=_confidence_scores(status="failed", selected_mods=[], profile=profile),
                output_dir=str(output_dir),
                next_actions=_next_actions("failed", foundation, [], failed_stage="discovery_empty"),
            )
            report.artifacts.extend(write_generation_reports(report, output_dir))
            return report
        stages.append(
            PipelineStageResult(
                name="discovery",
                status="completed",
                metadata={"candidates": len(discovery.candidates), "version": discovery.minecraft_version},
            )
        )

        sanitized = sanitize_candidates_for_profile(
            discovery.candidates,
            profile.model_copy(update={"minecraft_version": discovery.minecraft_version}),
            strict_profile_mode=strict_profile_mode,
        )
        stages.append(
            PipelineStageResult(
                name="candidate_sanitization",
                status="completed" if sanitized.candidates else "failed",
                metadata={"candidates": len(sanitized.candidates), "rejections": len(sanitized.rejected)},
            )
        )
        if not sanitized.candidates:
            diagnostics = _quality_gate_diagnostics(
                profile,
                [],
                [],
                strict_profile_mode=strict_profile_mode,
            )
            report = GenerationReport(
                run_id=run_id,
                status="failed",
                profile=profile,
                strict_profile_mode=strict_profile_mode,
                minecraft_version=discovery.minecraft_version,
                failed_stage="selection_quality_gate",
                stages=stages,
                search_plans=strategy.search_plans,
                rejected_mods=discovery.rejected + sanitized.rejected,
                performance_foundation=foundation,
                shader_support=_shader_support_report(foundation, []),
                shader_recommendations=foundation.shader_recommendations,
                confidence=_confidence_scores(
                    status="failed",
                    selected_mods=[],
                    foundation=foundation,
                    profile=profile,
                    quality_diagnostics=diagnostics,
                ),
                output_dir=str(output_dir),
                next_actions=_next_actions("failed", foundation, sanitized.rejected, failed_stage="selection_quality_gate"),
                **_diagnostics_without_selection_fields(diagnostics),
            )
            report.artifacts.extend(write_generation_reports(report, output_dir))
            return report

        scored = self.facade.score_candidates(
            sanitized.candidates,
            profile.model_copy(update={"minecraft_version": discovery.minecraft_version}),
        )
        selection = select_candidates(
            scored,
            max_mods=max_before_dependencies,
            profile=profile.model_copy(update={"minecraft_version": discovery.minecraft_version}),
            strict_profile_mode=strict_profile_mode,
        )
        selected_candidates = [
            candidate for candidate in scored if candidate.project_id in set(selection.selected_project_ids)
        ]
        foundation = foundation.model_copy(
            update={"selected_mods": _foundation_selected_ids(selected_candidates, foundation)}
        )
        if not selected_candidates:
            report = GenerationReport(
                run_id=run_id,
                status="failed",
                profile=profile,
                strict_profile_mode=strict_profile_mode,
                minecraft_version=discovery.minecraft_version,
                failed_stage="selection_empty",
                stages=stages + [PipelineStageResult(name="selection", status="failed")],
                search_plans=strategy.search_plans,
                rejected_mods=discovery.rejected + sanitized.rejected + selection.rejected_mods,
                duplicate_system_warnings=_duplicate_warnings(selection.rejected_mods),
                pillar_coverage=selection.pillar_coverage,
                novelty_mods_selected=selection.novelty_mods_selected,
                performance_foundation_gaps=selection.performance_foundation_gaps,
                overrepresented_concepts=selection.overrepresented_concepts,
                performance_foundation=foundation,
                shader_support=_shader_support_report(foundation, selected_candidates),
                shader_recommendations=foundation.shader_recommendations,
                confidence=_confidence_scores(
                    status="failed",
                    selected_mods=selected_candidates,
                    foundation=foundation,
                    profile=profile,
                ),
                output_dir=str(output_dir),
                next_actions=_next_actions("failed", foundation, selection.rejected_mods, failed_stage="selection_empty"),
            )
            report.artifacts.extend(write_generation_reports(report, output_dir))
            return report

        gate_rejections = _selection_quality_gate(
            profile,
            selected_candidates,
            selection.rejected_mods,
            max_before_dependencies=max_before_dependencies,
            strict_profile_mode=strict_profile_mode,
            selection=selection,
        )
        diagnostics = _quality_gate_diagnostics(
            profile,
            selected_candidates,
            selection.rejected_mods,
            strict_profile_mode=strict_profile_mode,
            selection=selection,
        )
        if gate_rejections:
            report = GenerationReport(
                run_id=run_id,
                status="failed",
                profile=profile,
                strict_profile_mode=strict_profile_mode,
                minecraft_version=discovery.minecraft_version,
                failed_stage="selection_quality_gate",
                stages=stages
                + [
                    PipelineStageResult(
                        name="selection_quality_gate",
                        status="failed",
                        metadata={"rejections": len(gate_rejections)},
                    )
                ],
                search_plans=strategy.search_plans,
                selected_mods=selected_candidates,
                selected_theme_mods=_theme_mods(selected_candidates, foundation),
                selected_foundation_mods=_foundation_mods(selected_candidates, foundation),
                rejected_mods=discovery.rejected + sanitized.rejected + selection.rejected_mods + gate_rejections,
                duplicate_system_warnings=_duplicate_warnings(selection.rejected_mods),
                pillar_coverage=selection.pillar_coverage,
                novelty_mods_selected=selection.novelty_mods_selected,
                performance_foundation_gaps=selection.performance_foundation_gaps,
                overrepresented_concepts=selection.overrepresented_concepts,
                performance_foundation=foundation,
                shader_support=_shader_support_report(foundation, selected_candidates),
                shader_recommendations=foundation.shader_recommendations,
                confidence=_confidence_scores(
                    status="failed",
                    selected_mods=selected_candidates,
                    foundation=foundation,
                    dependency_rejections=gate_rejections,
                    profile=profile,
                    quality_diagnostics=diagnostics,
                ),
                output_dir=str(output_dir),
                next_actions=_next_actions(
                    "failed",
                    foundation,
                    selection.rejected_mods,
                    failed_stage="selection_quality_gate",
                    diagnostics=diagnostics,
                ),
                **_diagnostics_without_selection_fields(diagnostics),
            )
            report.artifacts.extend(write_generation_reports(report, output_dir))
            return report

        expanded, dependency_rejections = await expand_required_dependencies(
            self.facade.modrinth, selected_candidates, profile, discovery.minecraft_version
        )
        stages.append(
            PipelineStageResult(
                name="dependency_expansion",
                status="completed" if not dependency_rejections else "failed",
                metadata={"candidates": len(expanded), "rejections": len(dependency_rejections)},
            )
        )

        expanded_project_ids = list(
            dict.fromkeys(
                selection.selected_project_ids
                + [
                    candidate.project_id
                    for candidate in expanded
                    if candidate.selection_type == "dependency_added"
                ]
            )
        )
        resolved = self.facade.resolve_dependencies(
            expanded_project_ids,
            expanded,
            profile.model_copy(update={"minecraft_version": discovery.minecraft_version}),
            request.loader_version,
        )
        if dependency_rejections or resolved.rejected_mods:
            failed_stage = "dependency_resolution"
            status = "failed"
        else:
            failed_stage = None
            status = "completed"

        artifacts = []
        validation = ValidationReport(status="skipped", details="Validation not run.")
        if status == "completed":
            pack = ResolvedPack(
                name=profile.name,
                minecraft_version=discovery.minecraft_version,
                loader=profile.loader,
                loader_version=request.loader_version,
                selected_mods=resolved.selected_mods,
                rejected_mods=resolved.rejected_mods,
                dependency_edges=resolved.dependency_edges,
            )
            try:
                artifacts.extend(await self.facade.build_pack(pack, output_dir, download=not request.dry_run))
                artifacts.append(self.facade.generate_configs(profile, output_dir))
                validation = self.facade.validate_launch(safe_slug(profile.name, fallback="pack"))
            except Exception as exc:
                status = "failed"
                failed_stage = "download_verification"
                stages.append(PipelineStageResult(name="build", status="failed", message=str(exc)))
        if status == "completed":
            stages.append(PipelineStageResult(name="build", status="completed", metadata={"artifacts": len(artifacts)}))

        report = GenerationReport(
            run_id=run_id,
            status=status,
            profile=profile,
            strict_profile_mode=strict_profile_mode,
            minecraft_version=discovery.minecraft_version,
            failed_stage=failed_stage,
            stages=stages,
            search_plans=strategy.search_plans,
            selected_mods=resolved.selected_mods if status == "completed" else expanded,
            selected_theme_mods=_theme_mods(selected_candidates, foundation),
            selected_foundation_mods=_foundation_mods(selected_candidates, foundation),
            dependency_added_mods=[candidate for candidate in expanded if candidate.selection_type == "dependency_added"],
            rejected_mods=discovery.rejected + sanitized.rejected + dependency_rejections + selection.rejected_mods + resolved.rejected_mods,
            dependency_edges=resolved.dependency_edges,
            conflicts=self.facade.detect_conflicts(selected_candidates),
            duplicate_system_warnings=_duplicate_warnings(selection.rejected_mods),
            pillar_coverage=selection.pillar_coverage,
            novelty_mods_selected=selection.novelty_mods_selected,
            performance_foundation_gaps=selection.performance_foundation_gaps,
            overrepresented_concepts=selection.overrepresented_concepts,
            performance_foundation=foundation,
            shader_support=_shader_support_report(foundation, resolved.selected_mods if status == "completed" else selected_candidates),
            shader_recommendations=foundation.shader_recommendations,
            confidence=_confidence_scores(
                status=status,
                selected_mods=resolved.selected_mods if status == "completed" else expanded,
                foundation=foundation,
                dependency_rejections=dependency_rejections + resolved.rejected_mods,
                profile=profile,
                quality_diagnostics=diagnostics,
            ),
            artifacts=artifacts,
            validation=validation,
            output_dir=str(output_dir),
            next_actions=_next_actions(status, foundation, selection.rejected_mods, failed_stage=failed_stage, diagnostics=diagnostics),
            **_diagnostics_without_selection_fields(diagnostics),
        )
        report.artifacts.extend(write_generation_reports(report, output_dir))
        return report


def _foundation_selected_ids(
    candidates: list[CandidateMod], foundation: PerformanceFoundationReport
) -> list[str]:
    selected: list[str] = []
    queries = [query.lower() for query in foundation.search_targets]
    capabilities = {target.capability for target in foundation.targets}
    for candidate in candidates:
        text = candidate.searchable_text()
        if any(query in text for query in queries):
            selected.append(candidate.project_id)
            continue
        if "renderer_optimization" in capabilities and any(marker in text for marker in ("sodium", "renderer optimization")):
            selected.append(candidate.project_id)
        elif "shader_support" in capabilities and any(marker in text for marker in ("iris", "shader loader")):
            selected.append(candidate.project_id)
    return selected


def _diagnostics_without_selection_fields(diagnostics: dict) -> dict:
    explicit_fields = {
        "pillar_coverage",
        "novelty_mods_selected",
        "performance_foundation_gaps",
        "overrepresented_concepts",
    }
    return {key: value for key, value in diagnostics.items() if key not in explicit_fields}


def _foundation_mods(
    candidates: list[CandidateMod], foundation: PerformanceFoundationReport
) -> list[CandidateMod]:
    selected_ids = set(foundation.selected_mods)
    return [
        candidate.model_copy(update={"selection_type": "selected_foundation_mod"})
        for candidate in candidates
        if candidate.project_id in selected_ids
    ]


def _theme_mods(
    candidates: list[CandidateMod], foundation: PerformanceFoundationReport
) -> list[CandidateMod]:
    foundation_ids = set(foundation.selected_mods)
    return [candidate for candidate in candidates if candidate.project_id not in foundation_ids]


def _shader_support_report(
    foundation: PerformanceFoundationReport, candidates: list[CandidateMod]
) -> ShaderSupportReport:
    selected = [
        candidate.project_id
        for candidate in candidates
        if "iris" in candidate.searchable_text() or "shader loader" in candidate.searchable_text()
    ]
    if not foundation.shader_support_enabled:
        return ShaderSupportReport(enabled=False, reason="Shader support disabled by prompt opt-out.")
    return ShaderSupportReport(
        enabled=True,
        selected_project_ids=selected,
        installed=False,
        reason="Shader support mod selected." if selected else "Shader support requested; no compatible verified loader selected yet.",
    )


def _duplicate_warnings(rejected: list[RejectedMod]) -> list[str]:
    return [
        f"{rejection.title or rejection.project_id}: duplicate {rejection.detail}"
        for rejection in rejected
        if rejection.reason == "duplicate_capability_group"
    ]


def _budget_group(candidate: CandidateMod, foundation: PerformanceFoundationReport | None = None) -> str:
    if candidate.selection_type == "dependency_added":
        return "dependencies"
    if foundation and candidate.project_id in set(foundation.selected_mods):
        return "performance_foundation"
    capabilities = set(infer_candidate_capabilities(candidate))
    text = candidate.searchable_text()
    if capabilities & {"forest_worldgen", "overgrown_nature", "moss", "roots", "mushroom_biomes", "underground_biomes", "caves"}:
        return "theme_worldgen_structures_exploration"
    if capabilities & {"structures", "ruins", "dungeons", "temples", "village_expansion", "exploration"}:
        return "theme_worldgen_structures_exploration"
    if capabilities & {"survival_progression", "resource_scarcity", "cold_survival"} or "survival" in text:
        return "survival_gameplay"
    if capabilities & {"atmosphere", "ambient_sounds", "shader_support"}:
        return "atmosphere_audio_visual"
    if capabilities & {"maps", "waystones"} or any(term in text for term in ("map", "atlas", "waystone")):
        return "utilities"
    if any(term in text for term in ("sodium", "lithium", "ferritecore", "iris", "optimization", "performance")):
        return "performance_foundation"
    return "utilities"


def _quality_gate_diagnostics(
    profile,
    selected_mods: list[CandidateMod],
    selection_rejections: list[RejectedMod],
    *,
    strict_profile_mode: bool,
    selection=None,
) -> dict[str, object]:
    off_theme: list[str] = []
    explicit: list[str] = []
    forbidden: list[str] = []
    low_evidence: list[str] = []
    breakdown: dict[str, int] = {}
    selected_text = " ".join(candidate.searchable_text() for candidate in selected_mods)

    for candidate in selected_mods:
        group = _budget_group(candidate)
        breakdown[group] = breakdown.get(group, 0) + 1
        explicit_matches = candidate_exclusion_matches(candidate, profile)
        forbidden_matches = candidate_forbidden_capability_matches(candidate, profile)
        matched_terms, matched_capabilities = candidate_positive_evidence(candidate, profile)
        if explicit_matches:
            explicit.append(candidate.project_id)
        if forbidden_matches:
            forbidden.append(candidate.project_id)
        if strict_profile_mode and not matched_terms and not matched_capabilities and _budget_group(candidate) != "performance_foundation":
            low_evidence.append(candidate.project_id)
        if explicit_matches or forbidden_matches or (strict_profile_mode and candidate.project_id in low_evidence):
            off_theme.append(candidate.project_id)

    missing_required = [
        capability
        for capability in profile.required_capabilities
        if capability not in {"performance_foundation", "shader_support"}
        and not any(term in selected_text for term in capability_terms(capability))
    ]
    duplicate_groups = [
        rejection.detail or rejection.project_id
        for rejection in selection_rejections
        if rejection.reason == "duplicate_capability_group"
    ]
    performance_gaps = list(selection.performance_foundation_gaps) if selection else []
    novelty_selected = list(selection.novelty_mods_selected) if selection else [
        candidate.project_id for candidate in selected_mods if is_novelty_candidate(candidate)
    ]
    pillar_coverage = selection.pillar_coverage if selection else {}
    overrepresented = list(selection.overrepresented_concepts) if selection else []
    novelty_rejected = [
        rejection.project_id
        for rejection in selection_rejections
        if rejection.reason == "novelty_penalty_applied"
    ]

    if ("performance_foundation" in profile.required_capabilities or profile.foundation_policy.performance == "enabled") and performance_gaps:
        missing_required.append("performance_foundation")

    suggestions = []
    if missing_required:
        for capability in missing_required[:6]:
            if capability in {"ruins", "structures"}:
                suggestions.append("search_more_for_ruins_structures")
            elif capability in {"exploration", "dungeons"}:
                suggestions.append("search_more_for_exploration_dungeons")
            elif capability == "performance_foundation":
                suggestions.append("search_more_performance_foundation")
            else:
                suggestions.append(f"search_more_{capability}")
    if off_theme or low_evidence:
        suggestions.append("tighten_negative_keywords")
    if novelty_selected:
        suggestions.append("reduce_lava_novelty_candidates")
    if not suggestions:
        suggestions.append("broaden_profile_aligned_search_terms")

    targeted_terms: list[str] = []
    for capability in missing_required:
        if capability == "performance_foundation":
            targeted_terms.extend(["sodium", "lithium", "ferritecore", "entity culling"])
        else:
            targeted_terms.extend(capability_terms(capability))
    if any(cap in profile.required_capabilities + profile.preferred_capabilities for cap in ("volcanic_worldgen", "lava_caves", "caves")):
        targeted_terms.extend(["volcanic caves", "basalt", "lava caves", "mountains"])
    if any(cap in profile.required_capabilities + profile.preferred_capabilities for cap in ("ruins", "structures", "dungeons")):
        targeted_terms.extend(["ruins", "structures", "dungeons", "temples", "abandoned mines"])
    if any(cap in profile.required_capabilities + profile.preferred_capabilities for cap in ("villages", "frontier_villages")):
        targeted_terms.extend(["villages", "frontier villages", "outposts"])

    top_blockers: list[str] = []
    for capability in missing_required:
        top_blockers.append(f"Missing required capability: {capability}")
    if performance_gaps:
        top_blockers.append("Performance foundation incomplete: " + ", ".join(performance_gaps) + " missing")
    if novelty_selected:
        top_blockers.append("Novelty lava mods selected as theme candidates")
    if overrepresented:
        top_blockers.append("Overrepresented concepts: " + ", ".join(overrepresented[:3]))

    return {
        "off_theme_selected_mods": list(dict.fromkeys(off_theme)),
        "explicit_exclusion_violations": list(dict.fromkeys(explicit)),
        "forbidden_capability_violations": list(dict.fromkeys(forbidden)),
        "low_evidence_selected_mods": list(dict.fromkeys(low_evidence)),
        "missing_required_capabilities": missing_required,
        "duplicate_system_groups": duplicate_groups,
        "selected_mod_budget_breakdown": breakdown,
        "suggested_search_refinements": suggestions,
        "pillar_coverage": pillar_coverage,
        "overrepresented_concepts": overrepresented,
        "novelty_mods_selected": novelty_selected,
        "rejected_penalized_novelty_mods": novelty_rejected,
        "performance_foundation_gaps": performance_gaps,
        "suggested_targeted_searches": list(dict.fromkeys(targeted_terms)),
        "top_blockers": top_blockers[:5],
    }


def _selection_quality_gate(
    profile,
    selected_mods: list[CandidateMod],
    selection_rejections: list[RejectedMod],
    *,
    max_before_dependencies: int,
    strict_profile_mode: bool = False,
    selection=None,
) -> list[RejectedMod]:
    failures: list[RejectedMod] = []
    diagnostics = _quality_gate_diagnostics(
        profile,
        selected_mods,
        selection_rejections,
        strict_profile_mode=strict_profile_mode,
        selection=selection,
    )
    if len(selected_mods) > max_before_dependencies:
        failures.append(
            RejectedMod(
                project_id="selection",
                reason="selected_count_exceeds_pre_dependency_target",
                detail=f"{len(selected_mods)} selected before dependencies; max is {max_before_dependencies}.",
            )
        )

    violating = [
        candidate
        for candidate in selected_mods
        if candidate_exclusion_matches(candidate, profile)
        or candidate_forbidden_capability_matches(candidate, profile)
        or candidate.score.hard_reject_reason in {"explicit_exclusion", "forbidden_capability"}
    ]
    for candidate in violating:
        failures.append(
            RejectedMod(
                project_id=candidate.project_id,
                title=candidate.title,
                reason="selection_violates_negative_constraints",
                detail=", ".join(candidate_negative_matches(candidate, profile))
                or candidate.score.hard_reject_reason,
            )
        )

    placeholders = [
        candidate
        for candidate in selected_mods
        if candidate.title.strip().lower() in {candidate.project_id.lower(), candidate.slug.lower()}
    ]
    if placeholders and (profile.search_keywords or profile.required_capabilities):
        failures.append(
            RejectedMod(
                project_id="selection",
                reason="selected_unresolved_placeholders",
                detail=", ".join(candidate.project_id for candidate in placeholders[:8]),
            )
        )

    selected_text = " ".join(candidate.searchable_text() for candidate in selected_mods)
    for capability in profile.required_capabilities:
        if capability in {"performance_foundation", "shader_support"}:
            continue
        if not any(term in selected_text for term in capability_terms(capability)):
            failures.append(
                RejectedMod(
                    project_id="selection",
                    reason="missing_required_capability",
                    detail=capability,
                )
            )

    if selected_mods:
        average_relevance = sum(candidate.score.relevance for candidate in selected_mods) / len(selected_mods)
        if average_relevance < 6.0 and profile.search_keywords:
            failures.append(
                RejectedMod(
                    project_id="selection",
                    reason="low_theme_match",
                    detail=f"Average relevance {average_relevance:.2f} is below quality gate.",
                )
            )

    for project_id in diagnostics["low_evidence_selected_mods"]:
        failures.append(
            RejectedMod(
                project_id=project_id,
                reason="low_evidence_selected_mod",
                detail="Selected mod lacks strict profile evidence.",
            )
        )

    if diagnostics["off_theme_selected_mods"]:
        failures.append(
            RejectedMod(
                project_id="selection",
                reason="off_theme_selected_mods",
                detail=", ".join(diagnostics["off_theme_selected_mods"]),
            )
        )

    for capability in diagnostics.get("performance_foundation_gaps", []):
        # One rejection is enough to mark this as a gate failure while details stay in diagnostics.
        pass
    if diagnostics.get("performance_foundation_gaps"):
        failures.append(
            RejectedMod(
                project_id="selection",
                reason="performance_foundation_incomplete",
                detail=", ".join(diagnostics["performance_foundation_gaps"]),
            )
        )

    if diagnostics.get("novelty_mods_selected"):
        failures.append(
            RejectedMod(
                project_id="selection",
                reason="novelty_mods_selected",
                detail=", ".join(diagnostics["novelty_mods_selected"]),
            )
        )

    return failures


def _confidence_scores(
    *,
    status: str,
    selected_mods: list[CandidateMod],
    foundation: PerformanceFoundationReport | None = None,
    dependency_rejections: list[RejectedMod] | None = None,
    profile=None,
    quality_diagnostics: dict[str, object] | None = None,
) -> ConfidenceScores:
    dependency_rejections = dependency_rejections or []
    selected_count = len(selected_mods)
    foundation_selected = len(foundation.selected_mods) if foundation else 0
    shader_enabled = bool(foundation and foundation.shader_support_enabled)
    exclusion_violations = 0
    missing_required = 0
    unresolved_placeholders = 0
    irrelevant = 0
    if profile:
        exclusion_violations = sum(1 for candidate in selected_mods if candidate_negative_matches(candidate, profile))
        selected_text = " ".join(candidate.searchable_text() for candidate in selected_mods)
        missing_required = sum(
            1
            for capability in profile.required_capabilities
            if capability not in {"performance_foundation", "shader_support"}
            and not any(term in selected_text for term in capability_terms(capability))
        )
    unresolved_placeholders = sum(
        1
        for candidate in selected_mods
        if candidate.title.strip().lower() in {candidate.project_id.lower(), candidate.slug.lower()}
    )
    irrelevant = sum(1 for candidate in selected_mods if candidate.score.relevance <= 0 and candidate.selection_type != "dependency_added")
    diagnostics = quality_diagnostics or {}
    off_theme_count = len(diagnostics.get("off_theme_selected_mods", []))
    low_evidence_count = len(diagnostics.get("low_evidence_selected_mods", []))
    explicit_count = len(diagnostics.get("explicit_exclusion_violations", []))
    forbidden_count = len(diagnostics.get("forbidden_capability_violations", []))
    missing_required_count = len(diagnostics.get("missing_required_capabilities", []))
    utility_count = int(diagnostics.get("selected_mod_budget_breakdown", {}).get("utilities", 0)) if diagnostics else 0
    novelty_count = len(diagnostics.get("novelty_mods_selected", []))
    performance_gap_count = len(diagnostics.get("performance_foundation_gaps", []))
    pillar_gaps = sum(
        1
        for item in diagnostics.get("pillar_coverage", {}).values()
        if item.get("required") and not item.get("satisfied")
    ) if diagnostics else 0
    selected_denominator = max(selected_count, 1)
    penalty = (
        0.22 * exclusion_violations
        + 0.14 * missing_required
        + 0.1 * unresolved_placeholders
        + 0.18 * len(dependency_rejections)
        + 0.35 * (irrelevant / selected_denominator)
        + 0.25 * (off_theme_count / selected_denominator)
        + 0.2 * (low_evidence_count / selected_denominator)
        + 0.25 * explicit_count
        + 0.25 * forbidden_count
        + 0.12 * missing_required_count
        + 0.08 * max(0, utility_count - 3)
        + 0.12 * novelty_count
        + 0.16 * performance_gap_count
        + 0.15 * pillar_gaps
    )
    base_theme = min(1.0, selected_count / 8.0)
    base_coherence = 0.75 if selected_count else 0.0
    theme_match = max(0.0, min(1.0, base_theme - penalty))
    pack_coherence = max(0.0, base_coherence - penalty)
    if off_theme_count or explicit_count or forbidden_count or low_evidence_count:
        theme_match = min(theme_match, 0.6)
    if dependency_rejections and any(rejection.reason in {"off_theme_selected_mods", "low_evidence_selected_mod"} for rejection in dependency_rejections):
        pack_coherence = min(pack_coherence, 0.6)
    return ConfidenceScores(
        theme_match=theme_match,
        compatibility=0.9 if selected_count else 0.0,
        dependency_resolution=max(0.0, 0.35 - 0.1 * len(dependency_rejections)) if dependency_rejections else (0.95 if selected_count else 0.0),
        pack_coherence=pack_coherence,
        performance_foundation=0.2 if performance_gap_count else min(1.0, foundation_selected / 4.0),
        visual_foundation=0.8 if shader_enabled else 0.0,
        build_readiness=0.9 if status == "completed" else 0.2,
    )


def _next_actions(
    status: str,
    foundation: PerformanceFoundationReport,
    rejected: list[RejectedMod],
    *,
    failed_stage: str | None = None,
    diagnostics: dict[str, object] | None = None,
) -> list[str]:
    actions: list[str] = []
    if failed_stage == "discovery_empty":
        actions.extend(["broaden_search_terms", "revise_profile", "check_network"])
    elif failed_stage == "selection_quality_gate":
        actions.extend(["revise_profile", "adjust_search_keywords", "remove_excluded_terms", "reduce_mod_count"])
        diagnostics = diagnostics or {}
        missing = set(diagnostics.get("missing_required_capabilities", []))
        if missing & {"ruins", "structures"}:
            actions.append("search_more_for_ruins_structures")
        if missing & {"exploration", "dungeons"}:
            actions.append("search_more_for_exploration_dungeons")
        if "performance_foundation" in missing or diagnostics.get("performance_foundation_gaps"):
            actions.append("search_more_performance_foundation")
        if diagnostics.get("novelty_mods_selected"):
            actions.append("reduce_lava_novelty_candidates")
        if missing:
            actions.append("strengthen_archetype_keywords")
    elif failed_stage == "dependency_resolution":
        actions.extend(["inspect_unresolved_dependencies", "replace_problem_mods", "rerun_dry_run"])
    elif failed_stage == "download_verification":
        actions.extend(["retry_download", "check_modrinth_availability"])
    elif failed_stage == "validation_launch":
        actions.extend(["analyze_failure", "remove_or_replace_crashing_mod"])
    elif status != "completed":
        actions.extend(["broaden_search_terms", "revise_profile", "check_network"])
    if foundation.performance_enabled and not foundation.selected_mods:
        actions.append("search_more_performance_mods")
    if foundation.shader_support_enabled and not foundation.shader_recommendations.installed:
        actions.append("install_shader_manually")
    if any(rejection.reason == "duplicate_capability_group" for rejection in rejected):
        actions.append("replace_duplicate_system")
    if status == "completed":
        actions.append("configure_prism_for_validation")
    return list(dict.fromkeys(actions))
