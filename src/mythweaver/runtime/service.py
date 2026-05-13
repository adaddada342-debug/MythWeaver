from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable

from mythweaver.catalog.loaders import normalize_loader
from mythweaver.launcher.smoketest import inject_smoke_test_mod, locate_smoke_test_helper
from mythweaver.runtime.classifiers import classify_runtime_text
from mythweaver.runtime.contracts import RuntimeDiagnosis, RuntimeIssue, RuntimeLaunchReport, RuntimeLaunchRequest
from mythweaver.runtime.diagnosis import diagnose_runtime_failure, diagnoses_from_issues
from mythweaver.runtime.instance import create_runtime_instance
from mythweaver.runtime.java import choose_java, get_java_major_version
from mythweaver.runtime.launcher import build_launch_command
from mythweaver.runtime.loader_install import install_loader_runtime
from mythweaver.runtime.minecraft import prepare_minecraft_client
from mythweaver.runtime.monitor import ProcessLike, monitor_command
from mythweaver.runtime.repair_actions import actions_for_diagnoses, actions_for_issues


def run_runtime_validation(
    request: RuntimeLaunchRequest,
    *,
    fetch_json: Callable[[str], Any] | None = None,
    fetch_bytes: Callable[[str], bytes] | None = None,
    java_major_version_probe: Callable[[str], int | None] = get_java_major_version,
    process_factory: Callable[[list[str]], ProcessLike] | None = None,
) -> RuntimeLaunchReport:
    loader = normalize_loader(request.loader)
    cache_root = Path(request.output_root or Path.cwd() / ".test-output") / "runtime-cache"
    if loader != "fabric":
        loader_result = install_loader_runtime(loader, request.minecraft_version, cache_root / "loaders")
        return _report(request, status="failed", stage="install_loader", java_path=request.java_path, issues=loader_result.issues)
    java = choose_java(request.minecraft_version, request.java_path, major_version_probe=java_major_version_probe)
    if java.issue is not None:
        return _report(request, status="failed", stage="prepare", java_path=None, issues=[java.issue])
    try:
        minecraft = prepare_minecraft_client(request.minecraft_version, cache_root / "minecraft", fetch_json=fetch_json, fetch_bytes=fetch_bytes)
    except Exception as exc:
        issue = RuntimeIssue(
            kind="minecraft_client_prepare_failed",
            severity="fatal",
            confidence=0.85,
            message=f"Failed to prepare Minecraft client metadata/assets: {exc}",
            evidence=[type(exc).__name__, str(exc)],
        )
        return _report(request, status="failed", stage="download_minecraft", java_path=java.java_path, issues=[issue])
    loader_result = install_loader_runtime(
        loader,
        request.minecraft_version,
        cache_root / "loaders",
        loader_version=request.loader_version,
        fetch_json=fetch_json,
        fetch_bytes=fetch_bytes,
    )
    if loader_result.issues:
        return _report(request, status="failed", stage="install_loader", java_path=java.java_path, issues=loader_result.issues)
    try:
        instance = create_runtime_instance(request.model_copy(update={"loader": loader}), run_id=uuid.uuid4().hex[:12])
    except Exception as exc:
        issue = RuntimeIssue(
            kind="runtime_instance_prepare_failed",
            severity="fatal",
            confidence=0.9,
            message=f"Failed to create isolated runtime instance: {exc}",
            evidence=[type(exc).__name__, str(exc)],
        )
        return _report(request, status="failed", stage="prepare", java_path=java.java_path, issues=[issue])
    smoke_test_mod_used = False
    if request.inject_smoke_test:
        if request.smoke_test_helper_path:
            requested_helper = Path(request.smoke_test_helper_path)
            helper = requested_helper if requested_helper.is_file() else None
        else:
            helper = locate_smoke_test_helper(search_root=Path.cwd())
        if helper is None and request.require_smoke_test_proof:
            issue = _smoke_helper_missing_issue(request)
            report = RuntimeLaunchReport(
                status="failed",
                stage="prepare",
                instance_path=instance.root,
                minecraft_version=request.minecraft_version,
                loader=loader,
                loader_version=loader_result.runtime.loader_version if loader_result.runtime else request.loader_version,
                java_path=java.java_path,
                command_preview=[],
                exit_code=None,
                success_signal=None,
                issues=[issue],
                recommended_next_actions=actions_for_diagnoses(diagnoses_from_issues([issue])) or actions_for_issues([issue]),
                logs_scanned=[],
                warnings=loader_result.warnings,
                diagnoses=diagnoses_from_issues([issue]),
            )
            _write_runtime_artifacts(report, Path(instance.root), "")
            return report
        if helper is not None:
            injection = inject_smoke_test_mod(Path(instance.root), helper_mod_path=helper)
            smoke_test_mod_used = injection.status in {"injected", "already_present"}
            (Path(instance.root) / "smoke_test_injection_report.json").write_text(
                injection.model_dump_json(indent=2),
                encoding="utf-8",
            )
            if injection.status == "failed" and request.require_smoke_test_proof:
                issue = RuntimeIssue(
                    kind="smoke_test_helper_injection_failed",
                    severity="fatal",
                    confidence=0.95,
                    message="Failed to inject MythWeaver smoke-test helper into the isolated runtime instance.",
                    evidence=injection.errors or injection.notes,
                )
                report = RuntimeLaunchReport(
                    status="failed",
                    stage="prepare",
                    instance_path=instance.root,
                    minecraft_version=request.minecraft_version,
                    loader=loader,
                    loader_version=loader_result.runtime.loader_version if loader_result.runtime else request.loader_version,
                    java_path=java.java_path,
                    command_preview=[],
                    exit_code=None,
                    success_signal=None,
                    issues=[issue],
                    recommended_next_actions=actions_for_diagnoses(diagnoses_from_issues([issue])) or actions_for_issues([issue]),
                    logs_scanned=[],
                    warnings=loader_result.warnings,
                    diagnoses=diagnoses_from_issues([issue]),
                )
                _write_runtime_artifacts(report, Path(instance.root), "")
                return report
    command = build_launch_command(
        java_path=java.java_path or "java",
        memory_mb=request.memory_mb,
        minecraft=minecraft,
        loader=loader_result.runtime,
        game_dir=str(Path(instance.minecraft_dir)),
        offline_username=request.offline_username,
    )
    monitor = monitor_command(
        command,
        instance_path=Path(instance.root),
        timeout_seconds=request.timeout_seconds,
        success_grace_seconds=request.success_grace_seconds,
        stop_after_success=request.stop_after_success,
        require_smoke_test_proof=request.require_smoke_test_proof,
        minimum_stability_seconds=request.minimum_stability_seconds,
        smoke_test_mod_used=smoke_test_mod_used,
        evidence_dir=Path(instance.root),
        process_factory=process_factory,
    )
    issues = monitor.issues
    if monitor.status == "failed" and not issues:
        issues = classify_runtime_text(monitor.output_text)
    diagnoses = (
        _diagnoses_for_monitor_failure(monitor.output_text, monitor.logs_scanned, issues)
        if monitor.status != "passed"
        else []
    )
    report = RuntimeLaunchReport(
        status="timed_out" if monitor.status == "timed_out" else "passed" if monitor.status == "passed" else "failed",
        stage="monitor" if monitor.status in {"passed", "timed_out"} else "classify",
        instance_path=instance.root,
        minecraft_version=request.minecraft_version,
        loader=loader,
        loader_version=loader_result.runtime.loader_version if loader_result.runtime else request.loader_version,
        java_path=java.java_path,
        command_preview=command,
        exit_code=monitor.exit_code,
        success_signal=monitor.success_signal,
        issues=issues,
        recommended_next_actions=actions_for_diagnoses(diagnoses) or actions_for_issues(issues),
        logs_scanned=monitor.logs_scanned,
        warnings=loader_result.warnings,
        proof=monitor.proof,
        diagnoses=diagnoses,
    )
    _write_runtime_artifacts(report, Path(instance.root), monitor.output_text)
    return report


def _report(
    request: RuntimeLaunchRequest,
    *,
    status: str,
    stage: str,
    java_path: str | None,
    issues: list[RuntimeIssue],
) -> RuntimeLaunchReport:
    return RuntimeLaunchReport(
        status=status,  # type: ignore[arg-type]
        stage=stage,  # type: ignore[arg-type]
        instance_path=None,
        minecraft_version=request.minecraft_version,
        loader=normalize_loader(request.loader),
        loader_version=request.loader_version,
        java_path=java_path,
        command_preview=[],
        exit_code=None,
        success_signal=None,
        issues=issues,
        recommended_next_actions=actions_for_issues(issues),
        logs_scanned=[],
        warnings=[],
        diagnoses=diagnoses_from_issues(issues) if issues else [],
    )


def _diagnoses_for_monitor_failure(text: str, logs_scanned: list[str], issues: list[RuntimeIssue]) -> list[RuntimeDiagnosis]:
    issue_diagnoses = diagnoses_from_issues(issues)
    text_diagnoses = diagnose_runtime_failure(text, evidence_paths=logs_scanned)
    seen = {diagnosis.kind for diagnosis in issue_diagnoses}
    return issue_diagnoses + [diagnosis for diagnosis in text_diagnoses if diagnosis.kind not in seen]


def _smoke_helper_missing_issue(request: RuntimeLaunchRequest) -> RuntimeIssue:
    evidence = [
        "require_smoke_test_proof=True",
        "Set MYTHWEAVER_SMOKETEST_MOD_PATH, pass --smoke-test-helper-path, or build tooling/mythweaver-smoketest.",
    ]
    if request.smoke_test_helper_path:
        evidence.append(f"requested_helper={request.smoke_test_helper_path}")
    return RuntimeIssue(
        kind="smoke_test_helper_missing",
        severity="fatal",
        confidence=1.0,
        message="MythWeaver smoke-test helper jar is required for verified playable proof but was not found.",
        evidence=evidence,
    )


def _write_runtime_artifacts(report: RuntimeLaunchReport, output_dir: Path, evidence_text: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "runtime_launch_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    if evidence_text:
        (output_dir / "runtime_evidence.txt").write_text(evidence_text[-200_000:], encoding="utf-8")
    if report.proof is not None:
        (output_dir / "marker_summary.json").write_text(report.proof.model_dump_json(indent=2), encoding="utf-8")
    if any(issue.severity == "fatal" for issue in report.issues):
        (output_dir / "crash_analysis.json").write_text(
            report.model_copy(update={"command_preview": []}).model_dump_json(indent=2),
            encoding="utf-8",
        )
