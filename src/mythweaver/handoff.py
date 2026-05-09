from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mythweaver.builders.paths import safe_slug
from mythweaver.schemas.contracts import (
    AgentCheckReport,
    AgentPackReport,
    AgentWorkflowPromptReport,
    AgentWorkflowStep,
    CrashAnalysisReport,
    PackBlueprint,
    PackDesign,
    PackDesignReviewReport,
    RepairReport,
    SelectedModList,
    SelectedModReviewReport,
)


def create_cloud_handoff_bundle(
    *,
    concept: str,
    output_dir: Path,
    minecraft_version: str,
    loader: str,
    size: str,
    performance_priority: str,
    shaders: str,
    avoid_terms: str,
) -> dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    request = output_dir / "cloud_ai_request.md"
    schema = output_dir / "selected_mods.schema.json"
    example = output_dir / "example_selected_mods.json"
    readme = output_dir / "README_FOR_AI.md"

    request.write_text(
        _cloud_ai_request_text(
            concept=concept,
            minecraft_version=minecraft_version,
            loader=loader,
            size=size,
            performance_priority=performance_priority,
            shaders=shaders,
            avoid_terms=avoid_terms,
        ),
        encoding="utf-8",
    )
    schema.write_text(json.dumps(SelectedModList.model_json_schema(), indent=2, sort_keys=True), encoding="utf-8")
    example.write_text(
        json.dumps(
            {
                "name": "Example Pack",
                "summary": "Replace this with the user's concept.",
                "minecraft_version": minecraft_version,
                "loader": loader,
                "mods": [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Renderer optimization"},
                    {"slug": "lithium", "role": "foundation", "reason_selected": "Game logic optimization"},
                    {"slug": "iris", "role": "shader_support", "reason_selected": "Shader support"},
                ],
                "shader_recommendations": [],
                "notes": "Return valid JSON only.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    readme.write_text(
        "\n".join(
            [
                "# MythWeaver Cloud AI Handoff",
                "",
                "Upload or paste `cloud_ai_request.md` into ChatGPT, Claude, Gemini, or another cloud AI.",
                "Ask it to return `selected_mods.json` as valid JSON only.",
                "Do not include downloaded mods, jars, API keys, cache files, or local secrets.",
                "",
                "After you receive the JSON, run:",
                "",
                "```powershell",
                "python -m mythweaver.cli.main handoff validate selected_mods.json",
                "python -m mythweaver.cli.main build-from-list selected_mods.json --output output/generated/<pack-name>",
                "```",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "output_dir": str(output_dir),
        "cloud_ai_request": str(request),
        "selected_mods_schema": str(schema),
        "example_selected_mods": str(example),
        "readme": str(readme),
    }


def export_cloud_handoff_zip(*, concept: str, output_zip: Path) -> dict[str, str]:
    output_zip = Path(output_zip)
    slug = safe_slug(concept, fallback="mythweaver-handoff")
    staging = Path("output") / "handoff" / slug
    bundle = create_cloud_handoff_bundle(
        concept=concept,
        output_dir=staging,
        minecraft_version="1.20.1",
        loader="fabric",
        size="medium",
        performance_priority="balanced",
        shaders="recommendations only",
        avoid_terms="",
    )
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in Path(bundle["output_dir"]).glob("*"):
            if path.is_file() and _safe_handoff_file(path):
                archive.write(path, arcname=path.name)
    bundle["zip"] = str(output_zip)
    return bundle


def validate_selected_mods_file(path: Path, *, output_dir: Path | None = None) -> dict[str, Any]:
    path = Path(path)
    output_dir = Path(output_dir or path.parent)
    try:
        selected = SelectedModList.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError, OSError) as exc:
        prompt = write_cloud_ai_fix_selected_mods_prompt(path, output_dir=output_dir, validation_errors=str(exc))
        return {"valid": False, "errors": str(exc), "cloud_ai_fix_prompt": str(prompt)}
    return {"valid": True, "selected_mods": selected, "next_command": f"python -m mythweaver.cli.main verify-list {path}"}


def import_selected_mods_file(source: Path, *, output: Path) -> dict[str, str]:
    validation = validate_selected_mods_file(source, output_dir=Path(output).parent)
    if not validation["valid"]:
        return {"status": "failed", "cloud_ai_fix_prompt": validation["cloud_ai_fix_prompt"]}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    return {"status": "imported", "output": str(output)}


def write_cloud_ai_fix_selected_mods_prompt(
    selected_mods_path: Path,
    *,
    output_dir: Path,
    validation_errors: str | None = None,
    verify_report: AgentPackReport | None = None,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = output_dir / "cloud_ai_fix_selected_mods_prompt.md"
    original = Path(selected_mods_path).read_text(encoding="utf-8", errors="replace") if Path(selected_mods_path).is_file() else ""
    rejected = []
    minecraft_version = "unknown"
    loader = "fabric"
    if verify_report:
        minecraft_version = verify_report.minecraft_version
        loader = verify_report.loader
        rejected = [
            f"- {item.project_id}: {item.reason} {item.detail or ''}".strip()
            for item in verify_report.rejected_mods + verify_report.incompatible_mods + verify_report.unresolved_mods
        ]
    text = [
        "# Fix selected_mods.json for MythWeaver",
        "",
        "That JSON file is not in the format MythWeaver expects, or some selected mods failed verification.",
        "Some selected mods need extra mods or have incompatible requirements. MythWeaver wrote this prompt so a cloud AI can correct the list.",
        "",
        f"Required Minecraft version: {minecraft_version}",
        f"Required loader: {loader}",
        "",
        "Rejected or incompatible mods:",
        *(rejected or ["- See validation errors below."]),
        "",
        "Validation errors:",
        validation_errors or "None.",
        "",
        "Original selected_mods.json:",
        "```json",
        original,
        "```",
        "",
        "Instructions:",
        "- Replace incompatible or missing mods with real Modrinth mods for the required loader/version.",
        "- Keep the same JSON schema.",
        "- Do not invent mods.",
        "- return corrected selected_mods.json only. No Markdown, no commentary.",
    ]
    prompt.write_text("\n".join(text) + "\n", encoding="utf-8")
    return prompt


def write_cloud_ai_repair_prompt(repair_report_path: Path, *, output_dir: Path | None = None) -> Path:
    repair_report_path = Path(repair_report_path)
    output_dir = Path(output_dir or repair_report_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)
    repair = RepairReport.model_validate_json(repair_report_path.read_text(encoding="utf-8"))
    prompt = output_dir / "cloud_ai_repair_prompt.md"
    lines = [
        "# Cloud AI Repair Prompt",
        "",
        "Repair_report summary:",
        f"- Pack: {repair.pack_name}",
        f"- Failure type: {repair.crash_classification}",
        f"- Suspected mods: {', '.join(repair.suspected_mods) if repair.suspected_mods else 'none'}",
        "",
        "Repair options:",
    ]
    for option in repair.repair_options:
        lines.extend(
            [
                f"- {option.id}: {option.action_type} {option.target_slug or ''}",
                f"  Reason: {option.reason}",
                f"  Risk: {option.risk_level}; confidence: {option.confidence:.2f}",
            ]
        )
    lines.extend(
        [
            "",
            "Instructions:",
            "- Choose the safest fix or edit selected_mods.json.",
            "- Do not remove mods unless the selected repair option justifies it.",
            "- Return corrected selected_mods.json only if editing the list.",
        ]
    )
    prompt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return prompt


def write_cloud_ai_design_prompt(design: PackDesign, *, output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = output_dir / "cloud_ai_design_prompt.md"
    lines = [
        "# Improve this MythWeaver PackDesign",
        "",
        "MythWeaver generated a deterministic pack design blueprint. Improve only the blueprint, not a mod list.",
        "",
        "Current pack_design.json:",
        "```json",
        design.model_dump_json(indent=2),
        "```",
        "",
        "Instructions:",
        "- Return corrected pack_design.json only. No Markdown, no commentary.",
        "- Keep the same PackDesign schema.",
        "- Make the core gameplay loop concrete.",
        "- Make progression phases readable for the chosen archetype.",
        "- Keep required systems realistic and theme-aware.",
        "- Do not turn every pack into RPG/adventure.",
        "- Do not mention or target Prominence II unless the user explicitly asked for it.",
        "- Keep the design deterministic; do not include download URLs or unverified mods.",
    ]
    prompt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return prompt


def write_cloud_ai_design_repair_prompt(
    review_report: PackDesignReviewReport,
    *,
    output_dir: Path,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = output_dir / "cloud_ai_design_repair_prompt.md"
    issue_lines = [
        f"- [{issue.severity}] {issue.category}: {issue.title} - {issue.detail or ''}".strip()
        for issue in review_report.issues
    ]
    lines = [
        "# Repair this MythWeaver PackDesign",
        "",
        f"Score: {review_report.score}",
        f"Readiness: {review_report.readiness}",
        f"Verdict: {review_report.verdict}",
        "",
        "Issues:",
        *(issue_lines or ["- None."]),
        "",
        "Missing design elements:",
        *(f"- {item}" for item in review_report.missing_design_elements),
        "",
        "Current pack_design.json:",
        "```json",
        review_report.design.model_dump_json(indent=2),
        "```",
        "",
        "Instructions:",
        "- Return corrected pack_design.json only. No Markdown, no commentary.",
        "- Keep the same PackDesign schema.",
        "- Strengthen theme clarity, core loop, progression arc, pacing, and quality bar.",
        "- Match the archetype instead of forcing RPG, tech, horror, or magic systems.",
        "- Respect forbidden systems and anti-goals.",
        "- Do not include jars, download URLs, or unverifiable mod metadata.",
    ]
    prompt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return prompt


def write_cloud_ai_blueprint_selection_prompt(
    design_path: Path,
    blueprint: PackBlueprint,
    *,
    output_dir: Path,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = output_dir / "cloud_ai_selection_prompt.md"
    design_text = Path(design_path).read_text(encoding="utf-8", errors="replace") if Path(design_path).is_file() else ""
    lines = [
        "# Create selected_mods.json from a MythWeaver PackBlueprint",
        "",
        "Use the PackBlueprint to produce selected_mods.json only.",
        "Do not return commentary.",
        "",
        "PackDesign source:",
        "```json",
        design_text,
        "```",
        "",
        "PackBlueprint:",
        "```json",
        blueprint.model_dump_json(indent=2),
        "```",
        "",
        "selected_mods.json schema reminder:",
        "```json",
        json.dumps(
            {
                "name": blueprint.name,
                "summary": blueprint.summary,
                "minecraft_version": blueprint.minecraft_version,
                "loader": blueprint.loader,
                "mods": [
                    {"slug": "real-modrinth-slug", "role": "theme", "reason_selected": "Explain which blueprint slot this fills."}
                ],
                "shader_recommendations": [],
                "notes": "Optional compatibility assumptions.",
            },
            indent=2,
        ),
        "```",
        "",
        "Instructions:",
        "- Return selected_mods.json only. No Markdown, no commentary.",
        "- Keep the same selected_mods.json schema used by MythWeaver.",
        "- Use real mods from allowed verified sources only.",
        "- Do not invent mods.",
        "- Respect min/max slot guidance.",
        "- Prefer maintained, compatible mods.",
        "- Prioritize coherence over mod count.",
        "- Respect forbidden slots and avoid rules.",
        "- Preserve the archetype's intended experience.",
        "- Do not add RPG/tech/horror/etc. systems unless blueprint asks for them.",
        "- Preserve strong performance foundation slots.",
        "- Each reason_selected should name the blueprint slot or gameplay purpose it supports.",
    ]
    prompt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return prompt


def write_cloud_ai_improve_pack_prompt(report_path: Path, *, output_dir: Path | None = None) -> Path:
    report_path = Path(report_path)
    output_dir = Path(output_dir or report_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    prompt = output_dir / "cloud_ai_improve_pack_prompt.md"
    prompt.write_text(
        "\n".join(
            [
                "# Improve this MythWeaver pack",
                "",
                f"Pack: {report.get('name', 'unknown')}",
                f"Status: {report.get('status', 'unknown')}",
                f"Failed stage: {report.get('failed_stage', 'none')}",
                "",
                "Please improve mod choice while preserving compatibility.",
                "Return corrected selected_mods.json only.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return prompt


def write_cloud_ai_review_prompt(
    selected_mods_path: Path,
    review_report: SelectedModReviewReport,
    *,
    output_dir: Path,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = output_dir / "cloud_ai_review_prompt.md"
    original = Path(selected_mods_path).read_text(encoding="utf-8", errors="replace") if Path(selected_mods_path).is_file() else ""
    issue_lines = []
    for issue in (
        review_report.issues
        + review_report.duplicate_systems
        + review_report.risky_combinations
        + review_report.stale_or_low_signal_mods
        + review_report.novelty_or_off_theme_mods
    ):
        issue_lines.append(
            f"- [{issue.severity}] {issue.category}: {issue.title}"
            + (f" ({', '.join(issue.affected_mods)})" if issue.affected_mods else "")
        )
    pillar_lines = [
        f"- {pillar.pillar}: {pillar.status}"
        + (f" ({', '.join(pillar.matching_mods)})" if pillar.matching_mods else "")
        for pillar in review_report.pillars
        if pillar.status in {"missing", "thin", "overloaded"}
    ]
    design_issue_lines = []
    if review_report.pack_design_path or review_report.archetype:
        design_issue_lines.extend(
            [
                f"- Archetype: {review_report.archetype or 'unknown'}",
                f"- Design alignment score: {review_report.design_alignment_score}",
                f"- Missing required systems: {', '.join(review_report.missing_required_systems) if review_report.missing_required_systems else 'none'}",
                f"- Weak required systems: {', '.join(review_report.weak_required_systems) if review_report.weak_required_systems else 'none'}",
            ]
        )
        design_groups = [
            ("Anti-goal violations", review_report.anti_goal_violations),
            ("Progression gaps", review_report.progression_gaps),
            ("Pacing issues", review_report.pacing_issues),
            ("Config/datapack warnings", review_report.config_or_datapack_warnings),
        ]
        for label, group in design_groups:
            design_issue_lines.append(f"- {label}:")
            design_issue_lines.extend(
                [f"  - [{issue.severity}] {issue.category}: {issue.title}" for issue in group] or ["  - none"]
            )
        design_issue_lines.append("- System coverage:")
        design_issue_lines.extend(
            [f"  - {system}: {', '.join(mods)}" for system, mods in sorted(review_report.system_coverage.items())] or ["  - none"]
        )
    text = [
        "# Improve selected_mods.json for MythWeaver",
        "",
        "MythWeaver found list-quality issues before build. Use this report to revise the selected mod list.",
        "",
        f"Pack: {review_report.name}",
        f"Minecraft version: {review_report.minecraft_version}",
        f"Loader: {review_report.loader}",
        f"Score: {review_report.score}",
        f"Verdict: {review_report.verdict}",
        "",
        "Pillar problems:",
        *(pillar_lines or ["- None flagged."]),
        "",
        "Issues:",
        *(issue_lines or ["- None flagged."]),
        "",
        "Design-aware review:",
        *(design_issue_lines or ["- No PackDesign was supplied."]),
        "",
        "Suggested replacement searches:",
        *(f"- {term}" for term in review_report.recommended_replacement_searches),
        "",
        "Original selected_mods.json:",
        "```json",
        original,
        "```",
        "",
        "Instructions:",
        "- Return corrected selected_mods.json only. No Markdown, no commentary.",
        "- Keep the same schema.",
        "- Keep the pack's theme.",
        "- Match the PackDesign archetype and quality bar when one is supplied.",
        "- Prioritize coherence over mod count.",
        "- Replace risky, stale, off-theme, or duplicate mods with real Modrinth mods.",
        "- Do not invent mods.",
        "- Prefer maintained Modrinth projects.",
        "- Add missing required systems.",
        "- Remove redundant, off-theme, stale, risky, or low-signal mods.",
        "- Preserve strong foundation mods unless the report specifically flags them.",
        "- Respect forbidden systems.",
        "- Do not add RPG systems unless the design calls for RPG systems.",
        "- Do not add tech systems unless the design allows tech.",
        "- Do not add horror systems unless the design allows horror.",
        "- Keep the pack realistic to build and fun to play.",
        "- Do not add huge mod counts just to fill categories.",
    ]
    prompt.write_text("\n".join(text) + "\n", encoding="utf-8")
    return prompt


def write_agent_workflow_prompt(
    concept_path: Path,
    concept_text: str,
    *,
    output_dir: Path,
) -> AgentWorkflowPromptReport:
    concept_path = Path(concept_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = output_dir / "cursor_composer_prompt.md"
    manifest_path = output_dir / "workflow_manifest.json"
    name = _agent_workflow_name(concept_path, concept_text)
    concept_command = str(concept_path)
    output_command = str(output_dir)
    selected_placeholder = "<selected_mods.json>"
    bundled_python = r"C:\Users\Adrian Iliev\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

    steps = [
        AgentWorkflowStep(
            step_id="01_concept",
            title="Read the concept",
            purpose="Understand the user's original pack fantasy before making creative decisions.",
            expected_outputs=[str(concept_path)],
            success_criteria=["The concept, target mood, and constraints are clear."],
            failure_handling=["Ask the user for clarification only if the concept is too ambiguous to preserve."],
        ),
        AgentWorkflowStep(
            step_id="02_design_pack",
            title="Create PackDesign",
            purpose="Use MythWeaver to turn the concept into a deterministic design artifact.",
            command=f"PYTHONPATH=src python -m mythweaver.cli.main design-pack {concept_command} --output-dir {output_command}",
            expected_outputs=[f"{output_command}/pack_design.json", f"{output_command}/cloud_ai_design_prompt.md"],
            success_criteria=["pack_design.json exists and preserves the user fantasy."],
            failure_handling=["Repair the concept/design only enough to make the design concrete."],
        ),
        AgentWorkflowStep(
            step_id="03_review_design",
            title="Review PackDesign",
            purpose="Check the design for obvious gaps before selecting mods.",
            command=f"PYTHONPATH=src python -m mythweaver.cli.main review-design {output_command}/pack_design.json",
            expected_outputs=[f"{output_command}/design_review_report.json"],
            success_criteria=["Hard design contradictions are fixed or intentionally documented."],
            failure_handling=["Use design repair prompts for clarity, not to erase the user's theme."],
        ),
        AgentWorkflowStep(
            step_id="04_blueprint_pack",
            title="Create PackBlueprint",
            purpose="Generate a structured mod-selection blueprint for the creative agent.",
            command=f"PYTHONPATH=src python -m mythweaver.cli.main blueprint-pack {output_command}/pack_design.json",
            expected_outputs=[f"{output_command}/pack_blueprint.json", f"{output_command}/cloud_ai_selection_prompt.md"],
            success_criteria=["The blueprint gives enough slots to build a coherent selected_mods.json."],
            failure_handling=["Revise the design if the blueprint contradicts the concept."],
        ),
        AgentWorkflowStep(
            step_id="05_create_selected_mods",
            title="Create selected_mods.json",
            purpose="Cursor/Codex/Claude/Gemini makes the creative mod choices from the concept and blueprint.",
            expected_outputs=[selected_placeholder],
            success_criteria=["All entries are real source refs with clear roles, reasons, and acquisition status."],
            failure_handling=["Do not invent mods; leave a note or use MythWeaver source-search/source-inspect when unsure."],
        ),
        AgentWorkflowStep(
            step_id="05b_source_resolve",
            title="Resolve source acquisition",
            purpose="Confirm selected mods come from verified, policy-compatible sources before build/export.",
            command=f"PYTHONPATH=src python -m mythweaver.cli.main source-resolve {selected_placeholder} --mc-version 1.20.1 --loader fabric --sources modrinth,curseforge,local --target-export local_instance --output-dir {output_command}",
            expected_outputs=[f"{output_command}/source_resolve_report.json"],
            success_criteria=["Autonomous builds use verified_auto sources or explicitly documented manual/local validation."],
            failure_handling=["Replace manual_required or metadata_incomplete mods with verified alternatives unless the user accepts manual mode."],
        ),
        AgentWorkflowStep(
            step_id="06_agent_check",
            title="Run agent-check",
            purpose="Ask MythWeaver for backend verification facts and AI-readable repair signals.",
            command=(
                f"PYTHONPATH=src python -m mythweaver.cli.main agent-check {selected_placeholder} "
                f"--against {output_command}/pack_design.json --output-dir {output_command}"
            ),
            expected_outputs=[f"{output_command}/agent_check_report.json", f"{output_command}/cloud_ai_agent_repair_prompt.md"],
            success_criteria=["No hard blockers remain before build/export."],
            failure_handling=["Fix all hard blockers; treat warnings and ai_judgment_needed as signals, not absolute commands."],
        ),
        AgentWorkflowStep(
            step_id="07_fix_blockers",
            title="Repair selected_mods.json",
            purpose="Creatively revise the list while respecting hard technical facts.",
            expected_outputs=[selected_placeholder],
            success_criteria=["Unsupported loader/version issues, missing dependencies, and invalid mods are fixed."],
            failure_handling=["If a mod is removed, explain why and choose a replacement or leave a clear note."],
        ),
        AgentWorkflowStep(
            step_id="08_verify_list",
            title="Verify selected mods",
            purpose="Confirm real Modrinth loader/version/file metadata for the chosen list.",
            command=f"PYTHONPATH=src python -m mythweaver.cli.main verify-list {selected_placeholder}",
            expected_outputs=["verify-list JSON output"],
            success_criteria=["No unsupported loader/version issues or unresolved projects remain."],
            failure_handling=["Replace or remove broken mods and rerun agent-check."],
        ),
        AgentWorkflowStep(
            step_id="09_build_dry_run",
            title="Dry-run package",
            purpose="Exercise build/export planning without downloading mods.",
            command=f"PYTHONPATH=src python -m mythweaver.cli.main build-from-list {selected_placeholder} --dry-run",
            expected_outputs=["generation_report.json", "generation_report.md", "dry-run .mrpack manifest"],
            success_criteria=["Dry run completes without technical blockers or do_not_build technical review."],
            failure_handling=["Use repair-pack or agent-check reports to update selected_mods.json."],
        ),
        AgentWorkflowStep(
            step_id="10_launch_check",
            title="Prove runtime stability",
            purpose="Dry-run is not playable proof; validate launch and world join before calling the pack done.",
            command=f"PYTHONPATH=src python -m mythweaver.cli.main launch-check {selected_placeholder} --pack-dir {output_command}",
            expected_outputs=[f"{output_command}/launch_validation_report.json"],
            success_criteria=["Launch validation passes or manual validation evidence is recorded."],
            failure_handling=["If the pack crashes, run analyze-crash and stabilize-pack instead of asking the user to debug stacktraces."],
        ),
        AgentWorkflowStep(
            step_id="11_stabilize_pack",
            title="Stabilize runtime crashes",
            purpose="Let MythWeaver analyze crash reports and produce a repaired selected_mods.json.",
            command=f"PYTHONPATH=src python -m mythweaver.cli.main stabilize-pack {selected_placeholder} --against {output_command}/pack_design.json --output-dir {output_command}",
            expected_outputs=[f"{output_command}/stabilization_report.json", f"{output_command}/selected_mods.stabilized.json"],
            success_criteria=["No known runtime crash remains unresolved."],
            failure_handling=["Use cloud_ai_crash_repair_prompt.md if deterministic repair is not safe."],
        ),
        AgentWorkflowStep(
            step_id="12_final_export",
            title="Export final pack only when safe",
            purpose="Build/export only after backend checks and runtime validation allow it.",
            expected_outputs=[f"{output_command}/<pack-name>.mrpack"],
            success_criteria=["No hard blockers, unsupported loader/version issues, missing dependencies, technical do_not_build review, or runtime crash."],
            failure_handling=["If build or launch fails, run repair-pack/stabilize-pack and update selected_mods.json."],
        ),
        AgentWorkflowStep(
            step_id="13_human_summary",
            title="Write final summary",
            purpose="Explain the final creative choices, technical status, and remaining cautions for a human.",
            expected_outputs=[f"{output_command}/final_summary.md"],
            success_criteria=["The summary is human-readable and makes removals/replacements auditable."],
            failure_handling=["Include unresolved cautions instead of hiding them."],
        ),
    ]

    prompt_lines = [
        "# Cursor/Codex MythWeaver Modpack Workflow",
        "",
        "You are the creative modpack designer.",
        "MythWeaver is your backend verification/build tool.",
        "",
        "Your responsibilities:",
        "- interpret the concept",
        "- make creative mod selection decisions",
        "- decide whether mods fit the theme",
        "- keep the pack fun and coherent",
        "- avoid bloat",
        "- repair selected_mods.json when MythWeaver reports technical issues",
        "",
        "MythWeaver responsibilities:",
        "- generate structure/design/blueprint",
        "- verify real mods",
        "- check loader/version support",
        "- resolve dependencies",
        "- report dropped mods",
        "- detect hard blockers",
        "- package/dry-run",
        "- launch-check/stabilize-pack runtime validation",
        "- generate repair prompts",
        "- resolve source acquisition policy across Modrinth, CurseForge, local files, and manual-only sources",
        "",
        "Concept:",
        "```markdown",
        concept_text.strip(),
        "```",
        "",
        "Workflow:",
        "1. Create/read the concept.",
        "2. Run design-pack.",
        "3. Run review-design.",
        "4. Run blueprint-pack.",
        "5. Use the blueprint and concept to create selected_mods.json.",
        "6. Run source-resolve to verify acquisition source, metadata confidence, hashes, and export policy.",
        "7. Run agent-check selected_mods.json --against pack_design.json.",
        "8. Fix all hard blockers.",
        "9. Treat warnings and ai_judgment_needed as signals, not absolute commands.",
        "10. Run verify-list.",
        "11. Run build-from-list --dry-run.",
        "12. Remember: dry-run is not final proof. A pack is not done after dry-run; dry-run is not enough.",
        "13. Run setup-launcher, then Prism launch-check or stabilize-pack. RAM and Fabric setup must be validated.",
        "14. Prism is the canonical runtime automation target. You must use Prism runtime validation where available.",
        "15. If the smoke-test helper jar is missing, build it with tooling/mythweaver-smoketest/build_smoketest.py or set MYTHWEAVER_SMOKETEST_MOD_PATH.",
        "16. You must inject the MythWeaver smoke-test helper mod if available.",
        "17. Required runtime proof is [MythWeaverSmokeTest] PLAYER_JOINED_WORLD plus STABLE_60_SECONDS at minimum; prefer STABLE_120_SECONDS for a 120 second check.",
        "18. Dry-run is not enough. Prism opening is not enough. Main menu is not enough. World join alone is not enough.",
        "19. If launch-check returns manual_required, report exactly what proof is missing.",
        "20. If launch automation cannot enter a world or smoke-test proof is unavailable, report manual_required with exact next steps.",
        "21. If launch-check returns crash, run analyze-crash, then stabilize-pack/autonomous-build repair loop.",
        "22. Remove optional unstable mods before asking the user to debug manually.",
        "23. Do not ask the user to manually debug stacktraces. Let MythWeaver repair or produce a repair prompt.",
        "24. Only export/build final pack if:",
        "    - no hard blockers",
        "    - no unsupported loader/version issues",
        "    - no missing required dependencies",
        "    - all autonomous sources are verified_auto or explicitly approved for manual/local validation",
        "    - no do_not_build technical review",
        "    - smoke-test runtime proof markers have passed; manual validation evidence is not stable unless it includes the required markers",
        "25. If build or launch fails, use repair-pack/stabilize-pack and update selected_mods.json.",
        "26. Save final files under output/generated/<pack-name>/.",
        "27. Produce a final human-readable summary.",
        "",
        "Hard rules:",
        "- Do not blindly obey MythWeaver subjective duplicate/theme signals.",
        "- Do not ignore hard technical blockers.",
        "- Do not silently drop mods.",
        "- Do not invent mods.",
        "- Prefer verified_auto sources for autonomous builds.",
        "- If a desired mod is manual_required, choose a verified alternative unless the user accepts manual mode.",
        "- Do not scrape CurseForge or Planet Minecraft.",
        "- Do not silently use external direct downloads.",
        "- Audit every source replacement or removal.",
        "- Do not hand the user a pack that only passed dry-run.",
        "- You must not call the pack stable unless runtime proof markers are observed.",
        "- Dry-run is not enough; Prism opening is not enough; main menu is not enough; world join alone is not enough.",
        "- Do not ask the user to manually edit vanilla/Fabric settings.",
        "- Do not ask the user to manually allocate RAM.",
        "- Use MythWeaver launcher setup tools.",
        "- If launcher automation is manual_required, produce exact instructions and then validate the resulting instance.",
        "- Use real Modrinth mods only.",
        "- Use CurseForge only through the official API when configured.",
        "- Treat Planet Minecraft as manual/discovery-only unless metadata, permission, download, hashes, loader, and Minecraft version can be proven.",
        "- Preserve the user's original pack fantasy.",
        "- Prefer coherence over mod count.",
        "- Keep changes auditable.",
        "- If a mod is removed, explain why and choose a replacement or leave a clear note.",
        "",
        "Command templates:",
        "```powershell",
        "PYTHONPATH=src python -m mythweaver.cli.main design-pack <concept.md> --output-dir <output_dir>",
        "PYTHONPATH=src python -m mythweaver.cli.main review-design <output_dir>/pack_design.json",
        "PYTHONPATH=src python -m mythweaver.cli.main blueprint-pack <output_dir>/pack_design.json",
        "PYTHONPATH=src python -m mythweaver.cli.main source-search \"<query>\" --mc-version 1.20.1 --loader fabric --sources modrinth,curseforge",
        "PYTHONPATH=src python -m mythweaver.cli.main source-inspect modrinth:<slug> --mc-version 1.20.1 --loader fabric",
        "PYTHONPATH=src python -m mythweaver.cli.main source-resolve <selected_mods.json> --mc-version 1.20.1 --loader fabric --sources modrinth,curseforge,local --target-export local_instance",
        "PYTHONPATH=src python -m mythweaver.cli.main agent-check <selected_mods.json> --against <output_dir>/pack_design.json --output-dir <output_dir>",
        "PYTHONPATH=src python -m mythweaver.cli.main verify-list <selected_mods.json>",
        "PYTHONPATH=src python -m mythweaver.cli.main build-from-list <selected_mods.json> --dry-run",
        "PYTHONPATH=src python tooling/mythweaver-smoketest/build_smoketest.py",
        "PYTHONPATH=src python -m mythweaver.cli.main setup-launcher <pack.mrpack> --launcher prism --instance-name <pack-name> --minecraft-version 1.20.1 --loader fabric --memory-mb 8192",
        "PYTHONPATH=src python -m mythweaver.cli.main stabilize-pack selected_mods.json --against pack_design.json",
        "PYTHONPATH=src python -m mythweaver.cli.main analyze-crash crash-report.txt --against selected_mods.json",
        "PYTHONPATH=src python -m mythweaver.cli.main launch-check --launcher prism --instance-path <instance-path> --wait-seconds 120 --inject-smoke-test-mod --validation-world",
        "PYTHONPATH=src python -m mythweaver.cli.main autonomous-build <concept.md> --launcher prism --memory-mb 8192",
        "```",
        "",
        "Commands for this concept:",
        "```powershell",
        f"PYTHONPATH=src python -m mythweaver.cli.main design-pack {concept_command} --output-dir {output_command}",
        f"PYTHONPATH=src python -m mythweaver.cli.main review-design {output_command}/pack_design.json",
        f"PYTHONPATH=src python -m mythweaver.cli.main blueprint-pack {output_command}/pack_design.json",
        f"PYTHONPATH=src python -m mythweaver.cli.main source-resolve {selected_placeholder} --mc-version 1.20.1 --loader fabric --sources modrinth,curseforge,local --target-export local_instance --output-dir {output_command}",
        (
            f"PYTHONPATH=src python -m mythweaver.cli.main agent-check {selected_placeholder} "
            f"--against {output_command}/pack_design.json --output-dir {output_command}"
        ),
        f"PYTHONPATH=src python -m mythweaver.cli.main verify-list {selected_placeholder}",
        f"PYTHONPATH=src python -m mythweaver.cli.main build-from-list {selected_placeholder} --dry-run",
        "PYTHONPATH=src python tooling/mythweaver-smoketest/build_smoketest.py",
        f"PYTHONPATH=src python -m mythweaver.cli.main setup-launcher <pack.mrpack> --launcher prism --instance-name {name!r} --minecraft-version 1.20.1 --loader fabric --memory-mb 8192 --output-dir {output_command}",
        f"PYTHONPATH=src python -m mythweaver.cli.main stabilize-pack {selected_placeholder} --against {output_command}/pack_design.json --output-dir {output_command}",
        f"PYTHONPATH=src python -m mythweaver.cli.main analyze-crash <crash-report.txt> --against {selected_placeholder} --output-dir {output_command}",
        f"PYTHONPATH=src python -m mythweaver.cli.main launch-check --launcher prism --instance-path <instance-path> --wait-seconds 120 --inject-smoke-test-mod --validation-world --output-dir {output_command}",
        "```",
        "",
        "Bundled Python fallback if normal python is unavailable:",
        "```powershell",
        f"& '{bundled_python}' -m mythweaver.cli.main design-pack {concept_command} --output-dir {output_command}",
        "```",
        "",
        "Use MythWeaver as factual backend evidence. You remain responsible for taste, theme fit, fun, pacing, and coherence.",
    ]
    prompt_path.write_text("\n".join(prompt_lines) + "\n", encoding="utf-8")

    report = AgentWorkflowPromptReport(
        name=name,
        concept_path=str(concept_path),
        output_dir=str(output_dir),
        prompt_path=str(prompt_path),
        workflow_manifest_path=str(manifest_path),
        recommended_steps=steps,
        summary=f"Wrote Cursor/Codex workflow prompt for {name}. This command does not build, download, or call AI.",
    )
    manifest_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def write_cloud_ai_agent_repair_prompt(
    selected_mods_path: Path,
    agent_check_report: AgentCheckReport,
    *,
    output_dir: Path,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = output_dir / "cloud_ai_agent_repair_prompt.md"
    original = Path(selected_mods_path).read_text(encoding="utf-8", errors="replace") if Path(selected_mods_path).is_file() else ""

    def finding_lines(findings: list) -> list[str]:
        return [
            f"- [{finding.severity}] {finding.kind}: {finding.title}"
            + (f" ({', '.join(finding.affected_mods)})" if finding.affected_mods else "")
            + (f" - {finding.detail}" if finding.detail else "")
            for finding in findings
        ] or ["- None."]

    text = [
        "# Repair selected_mods.json with MythWeaver facts",
        "",
        "You are the creative modpack designer.",
        "MythWeaver is the backend verification tool: it verifies Modrinth metadata, dependencies, compatibility memory, and build safety.",
        "Use hard blockers as must-fix items.",
        "Use warnings as technical caution.",
        "Use ai_judgment_needed findings to decide creatively.",
        "Preserve the user's theme.",
        "",
        f"Pack: {agent_check_report.name}",
        f"Minecraft version: {agent_check_report.minecraft_version}",
        f"Loader: {agent_check_report.loader}",
        f"Build permission: {agent_check_report.build_permission}",
        "",
        "Hard blockers:",
        *finding_lines(agent_check_report.hard_blockers),
        "",
        "Warnings:",
        *finding_lines(agent_check_report.warnings),
        "",
        "AI judgment needed:",
        *finding_lines(agent_check_report.ai_judgment_needed),
        "",
        "Suggested replacement searches:",
        *(f"- {term}" for term in agent_check_report.suggested_replacement_searches),
        "",
        "Original selected_mods.json:",
        "```json",
        original,
        "```",
        "",
        "Instructions:",
        "- Return corrected selected_mods.json only. No Markdown, no commentary.",
        "- Keep the same selected_mods.json schema.",
        "- Replace only mods that are broken, unsupported, risky, or clearly off-theme.",
        "- Do not blindly obey possible duplicate warnings if the mods are complementary.",
        "- Do not invent mods.",
        "- Prefer real maintained Modrinth projects.",
        "- Preserve strong foundation mods unless they are technically broken.",
        "- Preserve the pack identity and the user's theme.",
    ]
    prompt.write_text("\n".join(text) + "\n", encoding="utf-8")
    return prompt


def _agent_workflow_name(concept_path: Path, concept_text: str) -> str:
    for line in concept_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    if concept_path.stem:
        return concept_path.stem.replace("_", " ").replace("-", " ").title()
    return "MythWeaver Agent Workflow"


def write_cloud_ai_crash_repair_prompt(
    crash_report: CrashAnalysisReport,
    *,
    output_dir: Path,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = output_dir / "cloud_ai_crash_repair_prompt.md"
    finding_lines = [
        f"- [{finding.severity}] {finding.kind}: {finding.title}"
        + (f" ({', '.join(finding.suspected_mods)})" if finding.suspected_mods else "")
        + (f" - {finding.detail}" if finding.detail else "")
        for finding in crash_report.findings
    ]
    action_lines: list[str] = []
    for finding in crash_report.findings:
        action_lines.extend(f"- {action}" for action in finding.suggested_actions)
    text = [
        "# Runtime crash repair prompt",
        "",
        "You are the creative modpack designer. MythWeaver is the backend verifier.",
        "Use these hard facts from the crash to repair selected_mods.json without erasing the pack fantasy.",
        "",
        f"Status: {crash_report.status}",
        f"Crash report: {crash_report.crash_report_path}",
        f"Crashing mod: {crash_report.crashing_mod_id or 'unknown'}",
        f"Repair recommendation: {crash_report.repair_recommendation}",
        f"Summary: {crash_report.summary}",
        "",
        "Findings:",
        *(finding_lines or ["- None."]),
        "",
        "Suggested actions:",
        *(action_lines or ["- Manual review required."]),
        "",
        "Instructions:",
        "- preserve the pack fantasy.",
        "- prefer removing/replacing optional risky mods over manual hacks.",
        "- Do not ask the user to manually debug stacktraces.",
        "- Do not invent mods.",
        "- Use real Modrinth mods only.",
        "- Return corrected selected_mods.json if asked. No Markdown, no commentary.",
    ]
    prompt.write_text("\n".join(text) + "\n", encoding="utf-8")
    return prompt


def _cloud_ai_request_text(
    *,
    concept: str,
    minecraft_version: str,
    loader: str,
    size: str,
    performance_priority: str,
    shaders: str,
    avoid_terms: str,
) -> str:
    return "\n".join(
        [
            "# Create selected_mods.json for MythWeaver",
            "",
            "You are helping create a Minecraft Modrinth modpack list for MythWeaver.",
            "MythWeaver will verify every mod through Modrinth, resolve dependencies, and build the pack.",
            "",
            f"Concept: {concept}",
            f"Minecraft version: {minecraft_version}",
            f"Loader: {loader}",
            f"Approx size: {size}",
            f"Performance priority: {performance_priority}",
            f"Shaders: {shaders}",
            f"Things to avoid: {avoid_terms or 'none'}",
            "",
            "Return valid JSON only as selected_mods.json. Do not include Markdown.",
            "Use real Modrinth slugs or Modrinth project IDs only. Do not invent mods.",
            "Prefer Fabric 1.20.1 unless the user requested a custom target.",
            "Include performance foundation mods when appropriate.",
            "",
            "Expected shape:",
            "```json",
            json.dumps(
                {
                    "name": "Pack Name",
                    "summary": "Short summary.",
                    "minecraft_version": minecraft_version,
                    "loader": loader,
                    "mods": [
                        {"slug": "sodium", "role": "foundation", "reason_selected": "Renderer optimization"}
                    ],
                    "shader_recommendations": [],
                    "notes": "Any compatibility assumptions.",
                },
                indent=2,
            ),
            "```",
        ]
    )


def _safe_handoff_file(path: Path) -> bool:
    name = path.name.lower()
    return not (
        name.endswith(".jar")
        or name.endswith(".mrpack")
        or name == ".env"
        or name.endswith(".sqlite3")
        or "api_key" in name
    )
