from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from mythweaver.autopilot.contracts import AutopilotAttempt, AutopilotReport, AutopilotRequest
from mythweaver.autopilot.executor import apply_runtime_actions
from mythweaver.autopilot.limits import blocking_reasons
from mythweaver.autopilot.memory import AutopilotMemory
from mythweaver.autopilot.planner import plan_runtime_repairs
from mythweaver.autopilot.report import write_autopilot_report
from mythweaver.builders.source_instance import build_source_instance
from mythweaver.catalog.target_matrix import build_target_matrix
from mythweaver.runtime.contracts import RuntimeDiagnosis, RuntimeIssue, RuntimeLaunchReport, RuntimeLaunchRequest, RuntimeProof
from mythweaver.runtime.proof import proof_meets_requirement
from mythweaver.runtime.service import run_runtime_validation
from mythweaver.schemas.contracts import BuildArtifact, RequestedLoader, SelectedModList, SourceResolveReport
from mythweaver.sources.resolver import resolve_sources_for_selected_mods


async def run_autopilot(request: AutopilotRequest) -> AutopilotReport:
    selected_path = Path(request.selected_mods_path)
    selected = SelectedModList.model_validate_json(selected_path.read_text(encoding="utf-8"))
    output_root = Path(request.output_root or selected_path.parent / "autopilot")
    output_root.mkdir(parents=True, exist_ok=True)
    working = selected.model_copy(deep=True)
    if request.minecraft_version not in {"auto", "any"}:
        working.minecraft_version = request.minecraft_version
    if request.loader not in {"auto", "any"}:
        working.loader = cast(RequestedLoader, request.loader)
    memory = AutopilotMemory()
    attempts: list[AutopilotAttempt] = []
    final_export_path: str | None = None

    if working.minecraft_version in {"auto", "any"} or working.loader in {"auto", "any"}:
        matrix = await build_target_matrix(
            working,
            sources=request.sources,
            candidate_versions=request.candidate_versions or None,
            candidate_loaders=request.candidate_loaders or None,
            target_export=request.target_export,
            allow_manual_sources=request.allow_manual_sources,
        )
        (output_root / "target_matrix_report.json").write_text(matrix.model_dump_json(indent=2), encoding="utf-8")
        if matrix.best is None or matrix.status == "failed":
            report = _final_report(
                status="blocked",
                selected=working,
                request=request,
                attempts=attempts,
                summary="Target negotiation failed; inspect target_matrix_report.json.",
                final_instance_path=None,
                final_export_path=None,
                warnings=matrix.warnings,
            )
            write_autopilot_report(report, output_root)
            return report
        working.minecraft_version = matrix.best.minecraft_version
        working.loader = cast(RequestedLoader, matrix.best.loader)

    for attempt_number in range(1, request.max_attempts + 1):
        source_report = await resolve_sources_for_selected_mods(
            working,
            minecraft_version=working.minecraft_version,
            loader=working.loader,
            sources=request.sources,
            target_export="local_instance",
            autonomous=not request.allow_manual_sources,
            allow_manual_sources=request.allow_manual_sources,
        )
        build_status = source_report.status
        blocked = list(source_report.export_blockers)
        if source_report.status == "failed" or blocked or not source_report.export_supported:
            source_diagnosis = RuntimeDiagnosis(
                kind="source_policy_blocked",
                confidence="high",
                summary="Source/export policy blocked runtime-safe files for this attempt.",
                evidence=blocked or source_report.warnings or ["source resolution did not produce runtime-safe files"],
                blocking=True,
                suggested_repair_action_kinds=["manual_review"],
            )
            attempt = AutopilotAttempt(
                attempt_number=attempt_number,
                minecraft_version=working.minecraft_version,
                loader=working.loader,
                loader_version=request.loader_version,
                build_status=build_status,
                runtime_status="not_run",
                issues=[],
                actions_planned=[],
                actions_applied=[],
                blocked_reasons=blocked or source_report.warnings or ["source resolution did not produce runtime-safe files"],
                instance_path=None,
                diagnoses=[source_diagnosis],
            )
            attempts.append(attempt)
            report = _final_report(
                status="blocked",
                selected=working,
                request=request,
                attempts=attempts,
                summary="Source/export policy blocked runtime-safe build.",
                final_instance_path=None,
                final_export_path=final_export_path,
                warnings=source_report.warnings + blocked,
            )
            write_autopilot_report(report, output_root)
            return report
        try:
            artifact = _build_runtime_files(source_report, output_root, attempt_number, working.name, request.loader_version)
        except Exception as exc:
            build_diagnosis = RuntimeDiagnosis(
                kind="source_policy_blocked",
                confidence="medium",
                summary=f"Failed to build runtime input files: {exc}",
                evidence=[type(exc).__name__, str(exc)],
                blocking=True,
                suggested_repair_action_kinds=["manual_review"],
            )
            attempt = AutopilotAttempt(
                attempt_number=attempt_number,
                minecraft_version=working.minecraft_version,
                loader=working.loader,
                loader_version=request.loader_version,
                build_status="failed",
                runtime_status="not_run",
                issues=[],
                actions_planned=[],
                actions_applied=[],
                blocked_reasons=[build_diagnosis.summary],
                instance_path=None,
                diagnoses=[build_diagnosis],
            )
            attempts.append(attempt)
            report = _final_report(
                status="blocked",
                selected=working,
                request=request,
                attempts=attempts,
                summary="Runtime input build failed before launch.",
                final_instance_path=None,
                final_export_path=final_export_path,
                warnings=source_report.warnings,
            )
            write_autopilot_report(report, output_root)
            return report
        final_export_path = artifact.path
        mod_files = _runtime_mod_files(Path(artifact.path))
        runtime_report = run_runtime_validation(
            RuntimeLaunchRequest(
                instance_name=working.name,
                minecraft_version=working.minecraft_version,
                loader=working.loader,
                loader_version=request.loader_version,
                mod_files=mod_files,
                output_root=str(output_root),
                memory_mb=request.memory_mb,
                timeout_seconds=request.timeout_seconds,
                java_path=request.java_path,
                inject_smoke_test=request.inject_smoke_test,
                smoke_test_helper_path=request.smoke_test_helper_path,
                require_smoke_test_proof=request.require_smoke_test_proof,
                minimum_stability_seconds=request.minimum_stability_seconds,
            )
        )
        if runtime_report.status == "passed" and _runtime_verified(runtime_report, request):
            attempt = AutopilotAttempt(
                attempt_number=attempt_number,
                minecraft_version=working.minecraft_version,
                loader=working.loader,
                loader_version=runtime_report.loader_version,
                build_status=build_status,
                runtime_status=runtime_report.status,
                issues=[],
                actions_planned=[],
                actions_applied=[],
                blocked_reasons=[],
                instance_path=runtime_report.instance_path,
                proof=runtime_report.proof,
                diagnoses=runtime_report.diagnoses,
            )
            attempts.append(attempt)
            report = _final_report(
                status="verified_playable",
                selected=working,
                request=request,
                attempts=attempts,
                summary=_verified_summary(runtime_report),
                final_instance_path=runtime_report.instance_path,
                final_export_path=final_export_path,
                warnings=runtime_report.warnings,
                final_proof=runtime_report.proof,
            )
            write_autopilot_report(report, output_root)
            return report
        if runtime_report.status == "passed":
            proof_issue = RuntimeIssue(
                kind="runtime_proof_insufficient",
                severity="fatal",
                confidence=0.95,
                message="Runtime reported a weak pass, but Autopilot requires MythWeaver smoke-test world-join stability proof.",
                evidence=[runtime_report.proof.proof_level if runtime_report.proof else "no proof"],
            )
            runtime_report = runtime_report.model_copy(
                update={
                    "status": "failed",
                    "issues": [proof_issue],
                    "recommended_next_actions": [],
                }
            )
        planned = plan_runtime_repairs(runtime_report, request, memory)
        reasons = blocking_reasons(
            request=request,
            memory=memory,
            issues=runtime_report.issues,
            planned_actions=planned,
            attempt_count=attempt_number,
        )
        if reasons:
            attempt = AutopilotAttempt(
                attempt_number=attempt_number,
                minecraft_version=working.minecraft_version,
                loader=working.loader,
                loader_version=runtime_report.loader_version,
                build_status=build_status,
                runtime_status=runtime_report.status,
                issues=runtime_report.issues,
                actions_planned=planned,
                actions_applied=[],
                blocked_reasons=reasons,
                instance_path=runtime_report.instance_path,
                proof=runtime_report.proof,
                diagnoses=runtime_report.diagnoses,
            )
            attempts.append(attempt)
            report = _final_report(
                status="blocked" if "max attempts reached" not in reasons else "max_attempts_reached",
                selected=working,
                request=request,
                attempts=attempts,
                summary="Autopilot blocked: " + "; ".join(reasons),
                final_instance_path=runtime_report.instance_path,
                final_export_path=final_export_path,
                warnings=runtime_report.warnings,
                final_proof=runtime_report.proof,
            )
            write_autopilot_report(report, output_root)
            return report
        updated, applied = await apply_runtime_actions(
            working,
            planned,
            request,
            minecraft_version=working.minecraft_version,
            loader=working.loader,
            preflight_resolver=resolve_sources_for_selected_mods,
        )
        memory.record_attempt([working.minecraft_version, working.loader], runtime_report.issues, planned)
        attempts.append(
            AutopilotAttempt(
                attempt_number=attempt_number,
                minecraft_version=working.minecraft_version,
                loader=working.loader,
                loader_version=runtime_report.loader_version,
                build_status=build_status,
                runtime_status=runtime_report.status,
                issues=runtime_report.issues,
                actions_planned=planned,
                actions_applied=applied,
                blocked_reasons=[],
                instance_path=runtime_report.instance_path,
                proof=runtime_report.proof,
                diagnoses=runtime_report.diagnoses,
            )
        )
        if not any(item.status == "applied" for item in applied):
            report = _final_report(
                status="blocked",
                selected=working,
                request=request,
                attempts=attempts,
                summary="No planned repair action could be applied automatically.",
                final_instance_path=runtime_report.instance_path,
                final_export_path=final_export_path,
                warnings=runtime_report.warnings,
                final_proof=runtime_report.proof,
            )
            write_autopilot_report(report, output_root)
            return report
        working = updated

    report = _final_report(
        status="max_attempts_reached",
        selected=working,
        request=request,
        attempts=attempts,
        summary=f"Autopilot reached max_attempts={request.max_attempts}.",
        final_instance_path=attempts[-1].instance_path if attempts else None,
        final_export_path=final_export_path,
        warnings=[],
        final_proof=attempts[-1].proof if attempts else None,
    )
    write_autopilot_report(report, output_root)
    return report


def _build_runtime_files(
    source_report: SourceResolveReport,
    output_root: Path,
    attempt_number: int,
    name: str,
    loader_version: str | None,
) -> BuildArtifact:
    return build_source_instance(
        source_report,
        output_root / f"attempt-{attempt_number}" / "instances",
        name=name,
        loader_version=loader_version,
        prism=False,
    )


def _runtime_mod_files(instance_path: Path) -> list[str]:
    mods_dir = instance_path / ".minecraft" / "mods"
    return [os.fspath(path) for path in sorted(mods_dir.glob("*.jar"))]


def _final_report(
    *,
    status: str,
    selected: SelectedModList,
    request: AutopilotRequest,
    attempts: list[AutopilotAttempt],
    summary: str,
    final_instance_path: str | None,
    final_export_path: str | None,
    warnings: list[str],
    final_proof: RuntimeProof | None = None,
) -> AutopilotReport:
    return AutopilotReport(
        status=status,  # type: ignore[arg-type]
        final_minecraft_version=selected.minecraft_version,
        final_loader=selected.loader,
        final_loader_version=request.loader_version,
        attempts=attempts,
        final_instance_path=final_instance_path,
        final_export_path=final_export_path,
        summary=summary,
        warnings=warnings,
        final_proof=final_proof,
    )


def _runtime_verified(report: RuntimeLaunchReport, request: AutopilotRequest) -> bool:
    if not request.require_smoke_test_proof:
        return report.status == "passed"
    return proof_meets_requirement(report.proof, minimum_stability_seconds=request.minimum_stability_seconds)


def _verified_summary(report: RuntimeLaunchReport) -> str:
    proof = report.proof
    if proof is None:
        return "Runtime validation passed without structured proof details."
    return (
        f"Runtime validation passed with {proof.proof_level} proof; "
        f"stability={proof.stability_seconds_proven}s; "
        f"smoke_test_helper_used={proof.smoke_test_mod_used}; "
        f"evidence={proof.evidence_path or 'n/a'}."
    )
