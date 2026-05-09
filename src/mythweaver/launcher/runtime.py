from __future__ import annotations

from pathlib import Path

from mythweaver.launcher.detection import detect_launcher
from mythweaver.launcher.smoketest import inject_smoke_test_mod, remove_injected_smoke_test_mod
from mythweaver.launcher.validation_world import create_validation_world, remove_validation_world
from mythweaver.pipeline.crash_analysis import analyze_crash_report
from mythweaver.schemas.contracts import RuntimeSmokeTestReport, SelectedModList

SMOKE_MARKER_PREFIX = "[MythWeaverSmokeTest]"
SMOKE_MARKERS = (
    "CLIENT_READY",
    "SERVER_STARTING",
    "SERVER_STARTED",
    "PLAYER_JOINED_WORLD",
    "STABLE_30_SECONDS",
    "STABLE_60_SECONDS",
    "STABLE_120_SECONDS",
)


def run_launch_check(
    *,
    launcher: str,
    instance_path: Path | None,
    wait_seconds: int,
    output_dir: Path,
    selected: SelectedModList | None = None,
    crash_report: Path | None = None,
    latest_log: Path | None = None,
    inject_smoke_test: bool = False,
    smoke_test_mod_injected: bool = False,
    helper_mod_path: Path | None = None,
    validation_world: bool = False,
    keep_validation_world: bool = False,
    env: dict[str, str] | None = None,
) -> RuntimeSmokeTestReport:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if crash_report:
        crash_path = Path(crash_report)
        analysis = analyze_crash_report(
            crash_path.read_text(encoding="utf-8", errors="replace"),
            selected=selected,
            crash_report_path=str(crash_path),
        )
        return RuntimeSmokeTestReport(
            status="failed",
            stage="world_join" if any(finding.kind == "world_join_crash" for finding in analysis.findings) else "runtime_wait",
            seconds_observed=0,
            latest_log_path=str(latest_log) if latest_log else None,
            crash_report_path=str(crash_path),
            crash_analysis=analysis,
            summary="Launch-check failed from supplied crash report.",
            notes=["Crash analysis is included; repair selected_mods.json before calling the pack stable."],
            detected_markers=["crash"],
        )
    if latest_log:
        log_path = Path(latest_log)
        return _runtime_report_from_log(
            log_path,
            wait_seconds=wait_seconds,
            smoke_test_mod_injected=smoke_test_mod_injected,
            summary_if_missing="Supplied latest.log did not contain required MythWeaver smoke-test stability proof.",
        )
    injection_report = None
    world_report = None
    if instance_path and inject_smoke_test:
        injection_report = inject_smoke_test_mod(Path(instance_path), helper_mod_path=helper_mod_path)
        smoke_test_mod_injected = injection_report.status in {"injected", "already_present"}
        (output_dir / "smoke_test_injection_report.json").write_text(injection_report.model_dump_json(indent=2), encoding="utf-8")
    if instance_path and validation_world:
        world_report = create_validation_world(Path(instance_path))
    adapter = detect_launcher(launcher, env=env)
    launch = adapter.launch_instance(
        Path(instance_path or ""),
        wait_seconds=wait_seconds,
        output_dir=output_dir,
        inject_smoke_test=False,
        smoke_test_mod_injected=smoke_test_mod_injected,
        validation_world=validation_world,
        keep_validation_world=keep_validation_world,
    )
    if world_report is not None and not keep_validation_world:
        remove_validation_world(world_report)
    if injection_report is not None:
        remove_injected_smoke_test_mod(injection_report)
        (output_dir / "smoke_test_injection_report.json").write_text(injection_report.model_dump_json(indent=2), encoding="utf-8")
    if launch.log_path:
        log_report = _runtime_report_from_log(
            Path(launch.log_path),
            wait_seconds=wait_seconds,
            smoke_test_mod_injected=smoke_test_mod_injected,
            process_exit_code=launch.process_exit_code,
            freeze_detected=launch.freeze_detected,
            crash_report_path=launch.crash_report_path,
            evidence_path=launch.evidence_path,
            seconds_observed=launch.seconds_observed,
            summary_if_missing=launch.summary,
        )
        if launch.status == "failed":
            log_report.status = "failed"
            log_report.summary = launch.summary
        if launch.crash_report_path:
            log_report.status = "failed"
            log_report.crash_report_path = launch.crash_report_path
        crash_analysis = launch.crash_analysis
        if crash_analysis is None and launch.crash_report_path and Path(launch.crash_report_path).is_file():
            crash_analysis = analyze_crash_report(
                Path(launch.crash_report_path).read_text(encoding="utf-8", errors="replace"),
                selected=selected,
                crash_report_path=launch.crash_report_path,
            )
        log_report.crash_analysis = crash_analysis
        log_report.notes.extend(_runtime_notes(smoke_test_mod_injected, injection_report.status if injection_report else None))
        _attach_validation_world_report(log_report, world_report)
        return log_report
    crash_analysis = launch.crash_analysis
    if crash_analysis is None and launch.crash_report_path and Path(launch.crash_report_path).is_file():
        crash_analysis = analyze_crash_report(
            Path(launch.crash_report_path).read_text(encoding="utf-8", errors="replace"),
            selected=selected,
            crash_report_path=launch.crash_report_path,
        )
    report = RuntimeSmokeTestReport(
        status=launch.status if launch.status != "passed" or launch.required_markers_met else "manual_required",
        stage=launch.stage if launch.stage in {"not_started", "launcher_start", "main_menu", "world_create", "world_join", "runtime_wait", "complete"} else "not_started",
        seconds_observed=launch.seconds_observed,
        latest_log_path=launch.log_path,
        crash_report_path=launch.crash_report_path,
        crash_analysis=crash_analysis,
        summary=launch.summary if launch.status != "passed" else "Launch automation did not provide explicit smoke-test runtime proof.",
        notes=_runtime_notes(smoke_test_mod_injected, injection_report.status if injection_report else None),
        evidence_path=launch.evidence_path,
        detected_markers=launch.detected_markers,
        process_exit_code=launch.process_exit_code,
        freeze_detected=launch.freeze_detected,
        smoke_test_mod_injected=smoke_test_mod_injected,
        smoke_test_markers_seen=launch.smoke_test_markers_seen,
        marker_timestamps=launch.marker_timestamps,
        required_markers_met=launch.required_markers_met,
        stability_seconds_proven=launch.stability_seconds_proven,
        runtime_proof_observed=launch.runtime_proof_observed,
        final_export_excluded_smoketest_mod=True,
    )
    _attach_validation_world_report(report, world_report)
    return report


def _runtime_report_from_log(
    log_path: Path,
    *,
    wait_seconds: int,
    smoke_test_mod_injected: bool,
    summary_if_missing: str,
    process_exit_code: int | None = None,
    freeze_detected: bool = False,
    crash_report_path: str | None = None,
    evidence_path: str | None = None,
    seconds_observed: int = 0,
) -> RuntimeSmokeTestReport:
    markers = _detect_latest_log_markers(log_path)
    smoke_markers, marker_timestamps = parse_smoke_test_markers(log_path)
    stability = stability_seconds_from_markers(smoke_markers)
    required_met = required_smoke_markers_met(smoke_markers, wait_seconds=wait_seconds)
    crashed = "crash" in markers or bool(crash_report_path) or (process_exit_code is not None and process_exit_code != 0)
    if crashed:
        status = "failed"
        summary = "Launch-check failed from crash evidence."
    elif freeze_detected and not required_met:
        status = "failed"
        summary = "Runtime appears frozen before required MythWeaver smoke-test stability proof."
    elif smoke_markers:
        status = "passed" if required_met else "manual_required"
        summary = (
            f"Runtime smoke test passed with explicit MythWeaver markers through {stability} seconds."
            if required_met
            else "MythWeaver smoke-test markers were found, but required world join plus STABLE_60_SECONDS proof is missing."
        )
    else:
        status = "manual_required"
        summary = summary_if_missing
    stage = "complete" if required_met else "world_join" if "PLAYER_JOINED_WORLD" in smoke_markers or "world_join" in markers else "main_menu" if "main_menu" in markers else "launcher_start" if "launcher_start" in markers else "not_started"
    return RuntimeSmokeTestReport(
        status=status,
        stage=stage,
        seconds_observed=seconds_observed,
        latest_log_path=str(log_path),
        crash_report_path=crash_report_path,
        crash_analysis=None,
        summary=summary,
        notes=_runtime_notes(smoke_test_mod_injected, None),
        detected_markers=markers,
        evidence_path=evidence_path,
        process_exit_code=process_exit_code,
        freeze_detected=freeze_detected,
        smoke_test_mod_injected=smoke_test_mod_injected,
        smoke_test_markers_seen=smoke_markers,
        marker_timestamps=marker_timestamps,
        required_markers_met=required_met,
        stability_seconds_proven=stability,
        runtime_proof_observed=required_met,
        final_export_excluded_smoketest_mod=True,
    )


def write_runtime_smoke_report(report: RuntimeSmokeTestReport, output_dir: Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "runtime_smoke_test_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _detect_latest_log_markers(log_path: Path) -> list[str]:
    if not log_path.is_file():
        return []
    text = log_path.read_text(encoding="utf-8", errors="replace").lower()
    markers: list[str] = []
    if any(term in text for term in ("setting user:", "launching wrapped minecraft", "loading minecraft")):
        markers.append("launcher_start")
    if any(term in text for term in ("narrator library", "created: 1024x", "reloading resourcemanager", "sound engine started")):
        markers.append("main_menu")
    if any(term in text for term in ("preparing spawn area", "started integrated server", "joining world", "joined singleplayer server", "loaded 0 advancements")):
        markers.append("world_join")
    if any(term in text for term in ("---- minecraft crash report ----", "reported exception", "exception in thread", "caught previously unhandled exception")):
        markers.append("crash")
    return markers


def parse_smoke_test_markers(log_path: Path) -> tuple[list[str], dict[str, str]]:
    if not log_path.is_file():
        return [], {}
    markers: list[str] = []
    timestamps: dict[str, str] = {}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if SMOKE_MARKER_PREFIX not in line:
            continue
        for marker in SMOKE_MARKERS:
            if marker in line and marker not in markers:
                markers.append(marker)
                timestamps[marker] = _timestamp_from_log_line(line)
    return markers, timestamps


def stability_seconds_from_markers(markers: list[str]) -> int:
    if "STABLE_120_SECONDS" in markers:
        return 120
    if "STABLE_60_SECONDS" in markers:
        return 60
    if "STABLE_30_SECONDS" in markers:
        return 30
    return 0


def required_smoke_markers_met(markers: list[str], *, wait_seconds: int) -> bool:
    required = {"CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_60_SECONDS"}
    if not required.issubset(set(markers)):
        return False
    if wait_seconds >= 120 and "STABLE_120_SECONDS" in markers:
        return True
    return True


def _timestamp_from_log_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("[") and "]" in stripped:
        return stripped[1 : stripped.index("]")]
    return ""


def _runtime_notes(smoke_test_mod_injected: bool, injection_status: str | None) -> list[str]:
    notes = ["No fake success: pass requires MythWeaver smoke-test world-join and stability markers when available."]
    if smoke_test_mod_injected:
        notes.append("Smoke-test helper mod was used for deterministic runtime proof.")
    elif injection_status == "missing_helper":
        notes.append("Smoke-test helper mod was unavailable; runtime proof remains manual_required unless explicit markers are supplied.")
    return notes


def _attach_validation_world_report(report: RuntimeSmokeTestReport, world_report) -> None:
    if world_report is None:
        return
    report.validation_world_created = world_report.status in {"created", "already_present", "removed"}
    report.validation_world_cleaned = bool(world_report.removed_after_validation)
    report.validation_world_path = world_report.world_path
