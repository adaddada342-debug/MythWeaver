from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from mythweaver.autopilot.blockers import blocker_for_source_policy, blockers_from_runtime
from mythweaver.autopilot.contracts import AutopilotAttempt, AutopilotBlocker, AutopilotReport, AutopilotRequest
from mythweaver.autopilot.executor import apply_runtime_actions
from mythweaver.autopilot.limits import blocking_reasons
from mythweaver.autopilot.memory import AutopilotMemory
from mythweaver.autopilot.planner import plan_runtime_repairs
from mythweaver.autopilot.report import write_autopilot_report
from mythweaver.autopilot.timeline import TimelineWriter
from mythweaver.builders.source_instance import build_source_instance
from mythweaver.catalog.target_matrix import build_target_matrix
from mythweaver.core.settings import get_settings
from mythweaver.db.cache import SQLiteCache
from mythweaver.modrinth.client import ModrinthClient
from mythweaver.runtime.contracts import RuntimeDiagnosis, RuntimeIssue, RuntimeLaunchReport, RuntimeLaunchRequest, RuntimeProof
from mythweaver.runtime.diagnosis import diagnoses_from_issues
from mythweaver.runtime.proof import proof_meets_requirement
from mythweaver.runtime.service import run_runtime_validation
from mythweaver.schemas.contracts import BuildArtifact, RequestedLoader, SelectedModList, SourceResolveReport
from mythweaver.sources.resolver import resolve_sources_for_selected_mods


async def run_autopilot(request: AutopilotRequest) -> AutopilotReport:
    selected_path = Path(request.selected_mods_path)
    run_id = _effective_run_id(request)
    request = request.model_copy(update={"run_id": run_id})
    output_root = Path(request.output_root or selected_path.parent / "autopilot")
    run_dir = output_root / "runs" / run_id
    attempts_root = run_dir / "attempts"
    run_dir.mkdir(parents=True, exist_ok=True)
    attempts_root.mkdir(parents=True, exist_ok=True)
    request_path = run_dir / "request.json"
    timeline_path = run_dir / "timeline.jsonl"
    timeline = TimelineWriter(run_id=run_id, path=timeline_path)
    artifacts: dict[str, str] = {
        "run_dir": str(run_dir),
        "attempts_dir": str(attempts_root),
    }
    timeline.emit("run_started", summary="Autopilot run started.", data={"selected_mods_path": str(selected_path)})
    request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
    selected = SelectedModList.model_validate_json(selected_path.read_text(encoding="utf-8"))
    timeline.emit("request_loaded", summary="Selected mod list loaded.", data={"mods": len(selected.mods), "name": selected.name})
    initial_selection_path = run_dir / "working_selection.initial.json"
    latest_selection_path = run_dir / "working_selection.latest.json"
    target_state_path = run_dir / "target_state.json"
    memory_path = run_dir / "memory.json"
    working = selected.model_copy(deep=True)
    _write_model(initial_selection_path, working)
    _write_model(latest_selection_path, working)
    artifacts.update(
        {
            "working_selection_initial": str(initial_selection_path),
            "working_selection_latest": str(latest_selection_path),
            "target_state": str(target_state_path),
            "memory": str(memory_path),
        }
    )
    if request.minecraft_version not in {"auto", "any"}:
        working.minecraft_version = request.minecraft_version
    if request.loader not in {"auto", "any"}:
        working.loader = cast(RequestedLoader, request.loader)
    memory = AutopilotMemory()
    attempts: list[AutopilotAttempt] = []
    final_export_path: str | None = None

    settings = get_settings()
    cache = SQLiteCache(settings.cache_db)
    modrinth_client = ModrinthClient(
        base_url=settings.modrinth_base_url,
        user_agent=settings.modrinth_user_agent,
        cache=cache,
    )

    async def autopilot_preflight_resolve(
        preflight_selected: SelectedModList,
        *,
        minecraft_version: str,
        loader: str,
        sources: list[str],
        target_export: str,
        autonomous: bool,
        allow_manual_sources: bool = False,
    ) -> SourceResolveReport:
        return await resolve_sources_for_selected_mods(
            preflight_selected,
            minecraft_version=minecraft_version,
            loader=loader,
            sources=sources,
            target_export=target_export,
            autonomous=autonomous,
            allow_manual_sources=allow_manual_sources,
            modrinth=modrinth_client,
        )

    if working.minecraft_version in {"auto", "any"} or working.loader in {"auto", "any"}:
        timeline.emit(
            "target_negotiation_started",
            summary="Target negotiation started.",
            data={"candidate_versions": request.candidate_versions, "candidate_loaders": request.candidate_loaders},
        )
        matrix = await build_target_matrix(
            working,
            sources=request.sources,
            candidate_versions=request.candidate_versions or None,
            candidate_loaders=request.candidate_loaders or None,
            target_export=request.target_export,
            modrinth=modrinth_client,
            allow_manual_sources=request.allow_manual_sources,
        )
        matrix_path = run_dir / "target_matrix_report.json"
        matrix_path.write_text(matrix.model_dump_json(indent=2), encoding="utf-8")
        artifacts["target_matrix_report"] = str(matrix_path)
        if matrix.best is None or matrix.status == "failed":
            timeline.emit("target_negotiation_failed", status=matrix.status, summary="Target negotiation failed.", data={"warnings": matrix.warnings})
            report = _final_report(
                status="blocked",
                selected=working,
                request=request,
                attempts=attempts,
                summary="Target negotiation failed; inspect target_matrix_report.json.",
                final_instance_path=None,
                final_export_path=None,
                warnings=matrix.warnings,
                run_id=run_id,
                run_dir=run_dir,
                timeline_path=timeline_path,
                request_path=request_path,
                artifacts=artifacts,
                blockers=[
                    AutopilotBlocker(
                        kind="invalid_request",
                        message="Target negotiation failed for the requested constraints.",
                        severity="error",
                        agent_can_retry=True,
                        user_action_required=True,
                        suggested_next_step="Inspect target_matrix_report.json and adjust Minecraft version, loader, sources, or target export.",
                        data={"target_matrix_report": str(matrix_path), "warnings": matrix.warnings},
                    )
                ],
            )
            return _finalize_report(report, run_dir=run_dir, timeline=timeline)
        working.minecraft_version = matrix.best.minecraft_version
        working.loader = cast(RequestedLoader, matrix.best.loader)
        timeline.emit(
            "target_selected",
            status=matrix.status,
            summary=f"Selected target Minecraft {working.minecraft_version} / {working.loader}.",
            data=matrix.best.model_dump(mode="json"),
        )
    _write_target_state(target_state_path, working.minecraft_version, working.loader, request.loader_version)
    _write_model(latest_selection_path, working)
    if "target_matrix_report" not in artifacts:
        timeline.emit(
            "target_selected",
            status="fixed",
            summary=f"Using fixed target Minecraft {working.minecraft_version} / {working.loader}.",
            data={"minecraft_version": working.minecraft_version, "loader": working.loader, "loader_version": request.loader_version},
        )

    for attempt_number in range(1, request.max_attempts + 1):
        attempt_dir = attempts_root / f"attempt-{attempt_number:03d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        timeline.emit(
            "source_resolution_started",
            attempt_number=attempt_number,
            summary="Resolving runtime-installable source candidates.",
            data={"minecraft_version": working.minecraft_version, "loader": working.loader, "sources": request.sources},
        )
        source_report = await resolve_sources_for_selected_mods(
            working,
            minecraft_version=working.minecraft_version,
            loader=working.loader,
            sources=request.sources,
            target_export="local_instance",
            autonomous=not request.allow_manual_sources,
            allow_manual_sources=request.allow_manual_sources,
            modrinth=modrinth_client,
        )
        build_status = source_report.status
        blocked = list(source_report.export_blockers)
        timeline.emit(
            "source_resolution_completed",
            attempt_number=attempt_number,
            status=source_report.status,
            summary="Source resolution completed.",
            data={
                "export_supported": source_report.export_supported,
                "selected_files": len(source_report.selected_files),
                "manual_required": len(source_report.manual_required),
                "blocked": len(source_report.blocked),
                "export_blockers": source_report.export_blockers,
            },
        )
        if source_report.status == "failed" or blocked or not source_report.export_supported:
            evidence = blocked or source_report.warnings or ["source resolution did not produce runtime-safe files"]
            source_diagnosis = RuntimeDiagnosis(
                kind="source_policy_blocked",
                confidence="high",
                summary="Source/export policy blocked runtime-safe files for this attempt.",
                evidence=evidence,
                blocking=True,
                suggested_repair_action_kinds=["manual_review"],
            )
            blockers = [
                blocker_for_source_policy(
                    message=source_diagnosis.summary,
                    evidence=evidence,
                    attempt_number=attempt_number,
                )
            ]
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
                blockers=blockers,
            )
            attempts.append(attempt)
            timeline.emit("source_policy_blocked", attempt_number=attempt_number, status="blocked", summary=source_diagnosis.summary, data={"blockers": [item.model_dump(mode="json") for item in blockers]})
            timeline.emit("diagnosis_created", attempt_number=attempt_number, status="blocked", summary=source_diagnosis.summary, data=source_diagnosis.model_dump(mode="json"))
            timeline.emit("attempt_completed", attempt_number=attempt_number, status="blocked", summary="Attempt blocked before runtime validation.")
            report = _final_report(
                status="blocked",
                selected=working,
                request=request,
                attempts=attempts,
                summary="Source/export policy blocked runtime-safe build.",
                final_instance_path=None,
                final_export_path=final_export_path,
                warnings=source_report.warnings + blocked,
                run_id=run_id,
                run_dir=run_dir,
                timeline_path=timeline_path,
                request_path=request_path,
                artifacts=artifacts,
                blockers=blockers,
            )
            return _finalize_report(report, run_dir=run_dir, timeline=timeline)
        try:
            timeline.emit("build_started", attempt_number=attempt_number, summary="Building isolated local runtime input instance.")
            artifact = _build_runtime_files(source_report, attempt_dir, working.name, request.loader_version)
            timeline.emit("build_completed", attempt_number=attempt_number, status="resolved", summary="Runtime input instance built.", data={"path": artifact.path})
        except Exception as exc:
            build_diagnosis = RuntimeDiagnosis(
                kind="source_policy_blocked",
                confidence="medium",
                summary=f"Failed to build runtime input files: {exc}",
                evidence=[type(exc).__name__, str(exc)],
                blocking=True,
                suggested_repair_action_kinds=["manual_review"],
            )
            blockers = [
                blocker_for_source_policy(
                    message=build_diagnosis.summary,
                    evidence=build_diagnosis.evidence,
                    attempt_number=attempt_number,
                )
            ]
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
                blockers=blockers,
            )
            attempts.append(attempt)
            timeline.emit("build_failed", attempt_number=attempt_number, status="failed", summary=build_diagnosis.summary, data={"error": str(exc)})
            timeline.emit("attempt_completed", attempt_number=attempt_number, status="blocked", summary="Attempt blocked during runtime input build.")
            report = _final_report(
                status="blocked",
                selected=working,
                request=request,
                attempts=attempts,
                summary="Runtime input build failed before launch.",
                final_instance_path=None,
                final_export_path=final_export_path,
                warnings=source_report.warnings,
                run_id=run_id,
                run_dir=run_dir,
                timeline_path=timeline_path,
                request_path=request_path,
                artifacts=artifacts,
                blockers=blockers,
            )
            return _finalize_report(report, run_dir=run_dir, timeline=timeline)
        final_export_path = artifact.path
        mod_files = _runtime_mod_files(Path(artifact.path))
        timeline.emit(
            "runtime_validation_started",
            attempt_number=attempt_number,
            summary="Private runtime validation started.",
            data={"mod_files": len(mod_files), "evidence_dir": str(attempt_dir)},
        )
        runtime_report = run_runtime_validation(
            RuntimeLaunchRequest(
                instance_name=working.name,
                minecraft_version=working.minecraft_version,
                loader=working.loader,
                loader_version=request.loader_version,
                mod_files=mod_files,
                output_root=str(run_dir),
                evidence_output_dir=str(attempt_dir),
                memory_mb=request.memory_mb,
                timeout_seconds=request.timeout_seconds,
                java_path=request.java_path,
                inject_smoke_test=request.inject_smoke_test,
                smoke_test_helper_path=request.smoke_test_helper_path,
                require_smoke_test_proof=request.require_smoke_test_proof,
                minimum_stability_seconds=request.minimum_stability_seconds,
            )
        )
        timeline.emit(
            "runtime_validation_completed",
            attempt_number=attempt_number,
            status=runtime_report.status,
            summary=f"Runtime validation completed with status {runtime_report.status}.",
            data={
                "stage": runtime_report.stage,
                "exit_code": runtime_report.exit_code,
                "issues": [issue.kind for issue in runtime_report.issues],
                "diagnoses": [diagnosis.kind for diagnosis in runtime_report.diagnoses],
                "evidence_path": runtime_report.proof.evidence_path if runtime_report.proof else None,
            },
        )
        if runtime_report.proof is not None:
            timeline.emit(
                "proof_observed",
                attempt_number=attempt_number,
                status=runtime_report.proof.proof_level,
                summary=f"Runtime proof level observed: {runtime_report.proof.proof_level}.",
                data=runtime_report.proof.model_dump(mode="json"),
            )
        for diagnosis in runtime_report.diagnoses:
            timeline.emit(
                "diagnosis_created",
                attempt_number=attempt_number,
                status=diagnosis.kind,
                summary=diagnosis.summary,
                data=diagnosis.model_dump(mode="json"),
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
            timeline.emit("attempt_completed", attempt_number=attempt_number, status="verified_playable", summary="Attempt verified playable with strict proof.")
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
                run_id=run_id,
                run_dir=run_dir,
                timeline_path=timeline_path,
                request_path=request_path,
                artifacts=artifacts,
                blockers=[],
            )
            _write_model(latest_selection_path, working)
            _write_memory(memory_path, memory)
            return _finalize_report(report, run_dir=run_dir, timeline=timeline)
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
                    "diagnoses": diagnoses_from_issues([proof_issue]),
                }
            )
        planned = plan_runtime_repairs(runtime_report, request, memory)
        for action in planned:
            timeline.emit(
                "repair_planned",
                attempt_number=attempt_number,
                status=action.safety,
                summary=f"Planned {action.safety} repair: {action.action}.",
                data=action.model_dump(mode="json"),
            )
        reasons = blocking_reasons(
            request=request,
            memory=memory,
            issues=runtime_report.issues,
            planned_actions=planned,
            attempt_count=attempt_number,
        )
        if reasons:
            blockers = blockers_from_runtime(
                reasons=reasons,
                issues=runtime_report.issues,
                diagnoses=runtime_report.diagnoses,
                proof=runtime_report.proof,
                attempt_number=attempt_number,
            )
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
                blockers=blockers,
            )
            attempts.append(attempt)
            for blocker in blockers:
                timeline.emit("repair_blocked", attempt_number=attempt_number, status=blocker.kind, summary=blocker.message, data=blocker.model_dump(mode="json"))
            timeline.emit("attempt_completed", attempt_number=attempt_number, status="blocked", summary="Attempt blocked before applying a repair.")
            report = _final_report(
                status="max_attempts_reached" if reasons == ["max attempts reached"] else "blocked",
                selected=working,
                request=request,
                attempts=attempts,
                summary="Autopilot blocked: " + "; ".join(reasons),
                final_instance_path=runtime_report.instance_path,
                final_export_path=final_export_path,
                warnings=runtime_report.warnings,
                final_proof=runtime_report.proof,
                run_id=run_id,
                run_dir=run_dir,
                timeline_path=timeline_path,
                request_path=request_path,
                artifacts=artifacts,
                blockers=blockers,
            )
            _write_memory(memory_path, memory)
            return _finalize_report(report, run_dir=run_dir, timeline=timeline)
        updated, applied = await apply_runtime_actions(
            working,
            planned,
            request,
            minecraft_version=working.minecraft_version,
            loader=working.loader,
            preflight_resolver=autopilot_preflight_resolve,
        )
        for applied_action in applied:
            timeline.emit(
                "repair_applied" if applied_action.status == "applied" else "repair_blocked",
                attempt_number=attempt_number,
                status=applied_action.status,
                summary=applied_action.reason,
                data=applied_action.model_dump(mode="json"),
            )
        memory.record_attempt([working.minecraft_version, working.loader], runtime_report.issues, planned)
        _write_memory(memory_path, memory)
        _write_model(latest_selection_path, updated)
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
        timeline.emit("attempt_completed", attempt_number=attempt_number, status=runtime_report.status, summary="Attempt completed and repair actions were evaluated.")
        if not any(item.status == "applied" for item in applied):
            blockers = blockers_from_runtime(
                reasons=["no safe automatic repair is available"],
                issues=runtime_report.issues,
                diagnoses=runtime_report.diagnoses,
                proof=runtime_report.proof,
                attempt_number=attempt_number,
            )
            attempts[-1].blockers = blockers
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
                run_id=run_id,
                run_dir=run_dir,
                timeline_path=timeline_path,
                request_path=request_path,
                artifacts=artifacts,
                blockers=blockers,
            )
            return _finalize_report(report, run_dir=run_dir, timeline=timeline)
        working = updated
        _write_target_state(target_state_path, working.minecraft_version, working.loader, request.loader_version)

    blockers = [
        AutopilotBlocker(
            kind="max_attempts_reached",
            message=f"Autopilot reached max_attempts={request.max_attempts}.",
            severity="error",
            agent_can_retry=True,
            user_action_required=False,
            suggested_next_step="Review attempts and evidence, then retry with changed constraints if appropriate.",
            related_attempt=attempts[-1].attempt_number if attempts else None,
            evidence_path=attempts[-1].proof.evidence_path if attempts and attempts[-1].proof else None,
        )
    ]
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
        run_id=run_id,
        run_dir=run_dir,
        timeline_path=timeline_path,
        request_path=request_path,
        artifacts=artifacts,
        blockers=blockers,
    )
    return _finalize_report(report, run_dir=run_dir, timeline=timeline)


def _build_runtime_files(
    source_report: SourceResolveReport,
    attempt_dir: Path,
    name: str,
    loader_version: str | None,
) -> BuildArtifact:
    return build_source_instance(
        source_report,
        attempt_dir / "instances",
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
    run_id: str = "",
    run_dir: Path | None = None,
    timeline_path: Path | None = None,
    request_path: Path | None = None,
    artifacts: dict[str, str] | None = None,
    blockers: list[AutopilotBlocker] | None = None,
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
        run_id=run_id,
        run_dir=str(run_dir) if run_dir else "",
        timeline_path=str(timeline_path) if timeline_path else None,
        request_path=str(request_path) if request_path else None,
        artifacts=artifacts or {},
        blockers=blockers or _aggregate_blockers(attempts),
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


def _effective_run_id(request: AutopilotRequest) -> str:
    requested = request.run_id or request.resume_run_id
    if requested:
        return _sanitize_run_id(requested)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"mw_{stamp}_{uuid.uuid4().hex[:8]}"


def _sanitize_run_id(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    sanitized = sanitized.strip("._-")
    return sanitized[:80] or f"mw_{uuid.uuid4().hex[:8]}"


def _write_model(path: Path, model: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _write_target_state(path: Path, minecraft_version: str, loader: str, loader_version: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "minecraft_version": minecraft_version,
                "loader": loader,
                "loader_version": loader_version,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_memory(path: Path, memory: AutopilotMemory) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "issue_fingerprints": memory.issue_fingerprints,
                "action_fingerprints": memory.action_fingerprints,
                "target_fingerprints": sorted(memory.target_fingerprints),
                "changed_mods": sorted(memory.changed_mods),
                "issue_action_pairs": [list(item) for item in memory.issue_action_pairs],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _aggregate_blockers(attempts: list[AutopilotAttempt]) -> list[AutopilotBlocker]:
    blockers: list[AutopilotBlocker] = []
    seen: set[str] = set()
    for attempt in attempts:
        for blocker in attempt.blockers:
            key = f"{blocker.kind}|{blocker.related_attempt}|{blocker.message}"
            if key in seen:
                continue
            seen.add(key)
            blockers.append(blocker)
    return blockers


def _finalize_report(report: AutopilotReport, *, run_dir: Path, timeline: TimelineWriter) -> AutopilotReport:
    write_autopilot_report(report, run_dir)
    timeline.emit(
        "run_completed" if report.status != "failed" else "run_failed",
        status=report.status,
        summary=report.summary,
        data={
            "report_paths": report.report_paths,
            "blockers": [blocker.model_dump(mode="json") for blocker in report.blockers],
        },
    )
    return report
