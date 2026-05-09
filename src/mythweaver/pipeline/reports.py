from __future__ import annotations

import json
from pathlib import Path

from mythweaver.schemas.contracts import BuildArtifact, GenerationReport


def write_generation_reports(report: GenerationReport, output_dir: Path) -> list[BuildArtifact]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "generation_report.json"
    md_path = output_dir / "generation_report.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    lines = [
        f"# {report.profile.name}",
        "",
        f"- Status: {report.status}",
        f"- Strict profile mode: {'enabled' if report.strict_profile_mode else 'disabled'}",
        f"- Minecraft: {report.minecraft_version or 'unknown'}",
        f"- Failed stage: {report.failed_stage or 'none'}",
        f"- Selected mods: {len(report.selected_mods)}",
        f"- Rejected mods: {len(report.rejected_mods)}",
        f"- Performance foundation: {'enabled' if report.performance_foundation.performance_enabled else 'disabled'}",
        f"- Shader support: {'enabled' if report.shader_support.enabled else 'disabled'}",
        f"- Primary shader recommendation: {report.shader_recommendations.primary.name or 'none'}",
        f"- Validation: {report.validation.status}",
        "",
        "## Profile",
        f"- Themes: {', '.join(report.profile.themes) or 'none'}",
        f"- Terrain: {', '.join(report.profile.terrain) or 'none'}",
        f"- Gameplay: {', '.join(report.profile.gameplay) or 'none'}",
        f"- Mood: {', '.join(report.profile.mood) or 'none'}",
        f"- Desired systems: {', '.join(report.profile.desired_systems) or 'none'}",
        f"- Search keywords: {', '.join(report.profile.search_keywords) or 'none'}",
        f"- Negative keywords: {', '.join(report.profile.negative_keywords) or 'none'}",
        f"- Explicit exclusions: {', '.join(report.profile.explicit_exclusions) or 'none'}",
        f"- Required capabilities: {', '.join(report.profile.required_capabilities) or 'none'}",
        f"- Forbidden capabilities: {', '.join(report.profile.forbidden_capabilities) or 'none'}",
        "",
        "## Selection Diagnostics",
        f"- Off-theme selected mods: {', '.join(report.off_theme_selected_mods) or 'none'}",
        f"- Explicit exclusion violations: {', '.join(report.explicit_exclusion_violations) or 'none'}",
        f"- Forbidden capability violations: {', '.join(report.forbidden_capability_violations) or 'none'}",
        f"- Low-evidence selected mods: {', '.join(report.low_evidence_selected_mods) or 'none'}",
        f"- Missing required capabilities: {', '.join(report.missing_required_capabilities) or 'none'}",
        f"- Duplicate system groups: {', '.join(report.duplicate_system_groups) or 'none'}",
        f"- Budget breakdown: {json.dumps(report.selected_mod_budget_breakdown, sort_keys=True) if report.selected_mod_budget_breakdown else '{}'}",
        f"- Suggested search refinements: {', '.join(report.suggested_search_refinements) or 'none'}",
        "",
        "## Top Blockers",
    ]
    if report.top_blockers:
        lines.extend(f"{index}. {blocker}" for index, blocker in enumerate(report.top_blockers[:5], start=1))
    else:
        lines.append("- none")
    lines.extend(
        [
        "",
        "## Suggested Next Search Terms",
        ]
    )
    lines.extend(f"- {term}" for term in (report.suggested_targeted_searches[:12] or ["none"]))
    lines.extend(
        [
        "",
        "## Rejected/Penalized Novelty Mods",
        ]
    )
    lines.extend(f"- {project_id}" for project_id in (report.rejected_penalized_novelty_mods[:20] or ["none"]))
    lines.extend(
        [
        "",
        "## Search Plan Influence",
        ]
    )
    lines.extend(
        f"- {plan.query} | source: {plan.source_field or 'unknown'} | weight: {plan.weight:.1f} | origin: {plan.origin}"
        for plan in report.search_plans
    )
    lines.extend(
        [
        "",
        "## Foundation",
        f"- Selected foundation mods: {', '.join(report.performance_foundation.selected_mods) or 'none'}",
        f"- Shader support mods: {', '.join(report.shader_support.selected_project_ids) or 'none'}",
        f"- Shader install status: {'installed' if report.shader_recommendations.installed else 'recommended only'}",
        f"- Shader note: {report.shader_recommendations.install_reason}",
        "",
        "## Confidence",
        f"- Theme match: {report.confidence.theme_match:.2f}",
        f"- Compatibility: {report.confidence.compatibility:.2f}",
        f"- Dependency resolution: {report.confidence.dependency_resolution:.2f}",
        f"- Pack coherence: {report.confidence.pack_coherence:.2f}",
        f"- Performance foundation: {report.confidence.performance_foundation:.2f}",
        f"- Visual foundation: {report.confidence.visual_foundation:.2f}",
        f"- Build readiness: {report.confidence.build_readiness:.2f}",
        "",
        "## Selected Mods",
        ]
    )
    lines.append("### Theme Mods")
    lines.extend(f"- {mod.title} (`{mod.project_id}`)" for mod in report.selected_theme_mods or [])
    lines.append("### Foundation Mods")
    lines.extend(f"- {mod.title} (`{mod.project_id}`)" for mod in report.selected_foundation_mods or [])
    lines.append("### Dependency Added Mods")
    lines.extend(f"- {mod.title} (`{mod.project_id}`)" for mod in report.dependency_added_mods or [])
    if not (report.selected_theme_mods or report.selected_foundation_mods or report.dependency_added_mods):
        lines.extend(f"- {mod.title} (`{mod.project_id}`)" for mod in report.selected_mods)
    lines.append("")
    lines.append("## Rejected Candidates")
    lines.extend(
        f"- {rejection.title or rejection.project_id} (`{rejection.project_id}`): {rejection.reason}"
        + (f" - {rejection.detail}" if rejection.detail else "")
        for rejection in report.rejected_mods[:40]
    )
    lines.append("")
    lines.append("## Next Actions")
    lines.extend(f"- {action}" for action in (report.next_actions or ["No action required."]))
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [
        BuildArtifact(kind="generation-report-json", path=str(json_path)),
        BuildArtifact(kind="generation-report-md", path=str(md_path)),
    ]
