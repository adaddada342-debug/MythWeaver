from __future__ import annotations

from pathlib import Path

from mythweaver.autopilot.contracts import AutopilotReport


def write_autopilot_report(report: AutopilotReport, output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "autopilot_report.json"
    markdown_path = output_root / "autopilot_report.md"
    report.report_paths = {"json": str(json_path), "markdown": str(markdown_path)}
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_human_report(report), encoding="utf-8")


def render_human_report(report: AutopilotReport) -> str:
    lines = [
        f"# MythWeaver Autopilot: {report.status.replace('_', ' ').upper()}",
        "",
        "## Run",
        f"- Run id: {report.run_id or 'n/a'}",
        f"- Run dir: {report.run_dir or 'n/a'}",
        f"- Timeline: {report.timeline_path or 'n/a'}",
        "",
        "## Final target",
        f"- Minecraft: {report.final_minecraft_version or 'n/a'}",
        f"- Loader: {report.final_loader or 'n/a'} {report.final_loader_version or ''}".rstrip(),
        f"- Proof: {report.final_proof.proof_level if report.final_proof else 'n/a'}",
        f"- Stability seconds: {report.final_proof.stability_seconds_proven if report.final_proof else 0}",
        f"- Final instance: {report.final_instance_path or 'n/a'}",
        f"- JSON report: {report.report_paths.get('json', 'n/a')}",
        "",
        "## Attempts",
    ]
    for attempt in report.attempts:
        lines.append(f"{attempt.attempt_number}. build={attempt.build_status}; runtime={attempt.runtime_status}; issues={', '.join(issue.kind for issue in attempt.issues) or 'none'}")
        for diagnosis in attempt.diagnoses:
            lines.append(f"   - diagnosis: {diagnosis.kind} ({diagnosis.confidence}) {diagnosis.summary}")
        for applied in attempt.actions_applied:
            lines.append(f"   - {applied.status}: {applied.action.action} {applied.action.query or ''}".rstrip())
        for blocker in attempt.blockers:
            lines.append(f"   - blocker: {blocker.kind} ({blocker.severity}) {blocker.message}")
    if report.blockers:
        lines.extend(["", "## Blockers"])
        for blocker in report.blockers:
            next_step = f" Next: {blocker.suggested_next_step}" if blocker.suggested_next_step else ""
            lines.append(f"- {blocker.kind} ({blocker.severity}): {blocker.message}{next_step}")
    lines.extend(["", "## Summary", report.summary])
    if report.warnings:
        lines.extend(["", "## Warnings", *[f"- {warning}" for warning in report.warnings]])
    return "\n".join(lines) + "\n"
