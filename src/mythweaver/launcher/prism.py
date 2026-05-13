from __future__ import annotations

import os
import json
import shutil
import subprocess
import time
from pathlib import Path

from mythweaver.schemas.contracts import (
    LaunchValidationReport,
    LauncherDetectionReport,
    LauncherInstanceReport,
    LauncherValidationReport,
)

from .validation import validate_launcher_instance


class PrismLauncherAdapter:
    launcher_name = "prism"

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = env or dict(os.environ)

    def detect_installation(self) -> LauncherDetectionReport:
        data_paths = [str(path) for path in _prism_data_candidates(self.env) if path.exists()]
        executable_paths = [str(path) for path in _prism_executable_candidates(self.env) if path.exists()]
        status = "found" if data_paths or executable_paths else "not_found"
        notes = [] if status == "found" else ["Prism Launcher was not found in common local paths."]
        return LauncherDetectionReport(
            status=status,
            launcher_name=self.launcher_name,
            data_paths=data_paths,
            executable_paths=executable_paths,
            notes=notes,
        )

    def create_or_import_instance(
        self,
        pack_artifact: Path,
        *,
        instance_name: str,
        minecraft_version: str,
        loader: str,
        loader_version: str | None,
        memory_mb: int,
        output_dir: Path,
    ) -> LauncherInstanceReport:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        sibling_instance = Path(pack_artifact).parent / "instances" / _instance_id(instance_name)
        data_root = _first_existing_data_root(self.env)
        if data_root and sibling_instance.is_dir():
            instances_root = data_root / "instances"
            target = instances_root / sibling_instance.name
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(sibling_instance, target)
            return LauncherInstanceReport(
                status="created",
                launcher_name=self.launcher_name,
                instance_name=instance_name,
                instance_path=str(target),
                generated_instance_path=str(sibling_instance),
                prism_registered_instance_path=str(target),
                prism_instance_id=target.name,
                registered_with_prism=True,
                pack_artifact_path=str(pack_artifact),
                minecraft_version=minecraft_version,
                loader=loader,
                loader_version=loader_version,
                memory_mb=memory_mb,
                notes=[f"Copied generated Prism instance into {target}."],
            )
        if sibling_instance.is_dir():
            registration = _resolve_registered_instance(sibling_instance, self.env)
            return LauncherInstanceReport(
                status="created",
                launcher_name=self.launcher_name,
                instance_name=instance_name,
                instance_path=str(sibling_instance),
                generated_instance_path=str(sibling_instance),
                prism_registered_instance_path=str(registration[0]) if registration else None,
                prism_instance_id=registration[1] if registration else None,
                registered_with_prism=registration is not None,
                pack_artifact_path=str(pack_artifact),
                minecraft_version=minecraft_version,
                loader=loader,
                loader_version=loader_version,
                memory_mb=memory_mb,
                notes=[
                    "Using MythWeaver-generated Prism instance next to the pack artifact.",
                    "Instance is registered with Prism." if registration else "Instance is not registered with Prism; launch-check will require Prism registration.",
                ],
            )
        if data_root and Path(pack_artifact).is_dir():
            instances_root = data_root / "instances"
            target = instances_root / _instance_id(instance_name)
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(pack_artifact, target)
            return LauncherInstanceReport(
                status="created",
                launcher_name=self.launcher_name,
                instance_name=instance_name,
                instance_path=str(target),
                generated_instance_path=str(pack_artifact),
                prism_registered_instance_path=str(target),
                prism_instance_id=target.name,
                registered_with_prism=True,
                pack_artifact_path=str(pack_artifact),
                minecraft_version=minecraft_version,
                loader=loader,
                loader_version=loader_version,
                memory_mb=memory_mb,
                notes=[f"Copied Prism instance into {target}."],
            )
        instructions = output_dir / "launcher_import_instructions.md"
        instructions.write_text(
            "\n".join(
                [
                    "# Prism Launcher import instructions",
                    "",
                    "MythWeaver did not find enough local Prism configuration to safely create an instance directly.",
                    "1. Open Prism Launcher.",
                    f"2. Add Instance -> Import from zip -> choose `{pack_artifact}`.",
                    f"3. Name the instance `{instance_name}`.",
                    f"4. Confirm Minecraft `{minecraft_version}` and `{loader}` loader"
                    + (f" `{loader_version}`." if loader_version else "."),
                    f"5. Set maximum memory to at least `{memory_mb}` MB.",
                    "6. Run MythWeaver setup-launcher with --validate-only and --instance-path after import.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return LauncherInstanceReport(
            status="manual_required",
            launcher_name=self.launcher_name,
            instance_name=instance_name,
            pack_artifact_path=str(pack_artifact),
            minecraft_version=minecraft_version,
            loader=loader,
            loader_version=loader_version,
            memory_mb=memory_mb,
            notes=[f"Wrote Prism import/configuration instructions to {instructions}."],
        )

    def validate_instance(
        self,
        instance_path: Path,
        *,
        expected_minecraft_version: str,
        expected_loader: str,
        expected_loader_version: str | None,
        expected_memory_mb: int | None,
    ) -> LauncherValidationReport:
        return validate_launcher_instance(
            instance_path,
            launcher_name=self.launcher_name,
            expected_minecraft_version=expected_minecraft_version,
            expected_loader=expected_loader,
            expected_loader_version=expected_loader_version,
            expected_memory_mb=expected_memory_mb,
        )

    def launch_instance(
        self,
        instance_path: Path,
        *,
        wait_seconds: int,
        output_dir: Path,
        inject_smoke_test: bool = False,
        smoke_test_mod_injected: bool = False,
        validation_world: bool = False,
        keep_validation_world: bool = False,
    ) -> LaunchValidationReport:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        instance_path = Path(instance_path)
        log_path = _latest_log_path(instance_path)
        crash_before = _newest_crash_report(instance_path)
        evidence_path = output_dir / "runtime_evidence_report.json"
        executable = _first_existing_executable(self.env)
        if executable is None:
            report = _analyze_existing_runtime_evidence(
                instance_path=instance_path,
                wait_seconds=0,
                output_dir=output_dir,
                process_exit_code=None,
                freeze_detected=False,
                summary_if_missing="Prism executable was not found; launch automation cannot start.",
            )
            _write_evidence(evidence_path, report)
            report.evidence_path = str(evidence_path)
            return report
        registration = _resolve_registered_instance(instance_path, self.env)
        if registration is None:
            registration = _register_generated_instance_for_launch(instance_path, self.env)
            if registration is not None:
                instance_path = registration[0]
                log_path = _latest_log_path(instance_path)
        if registration is None:
            report = LaunchValidationReport(
                status="manual_required",
                stage="launcher_setup",
                summary=f"Prism instance is not registered with Prism instances root: {instance_path}",
                log_path=str(log_path) if log_path.exists() else None,
                seconds_observed=0,
                output_dir=str(output_dir),
                evidence_path=str(evidence_path),
                smoke_test_mod_injected=smoke_test_mod_injected,
                final_export_excluded_smoketest_mod=True,
            )
            _write_evidence(evidence_path, report)
            return report

        stdout_path = output_dir / "prism_stdout.log"
        stderr_path = output_dir / "prism_stderr.log"
        registered_instance_path, instance_id = registration
        instance_path = registered_instance_path
        log_path = _latest_log_path(instance_path)
        command = [str(executable), "--launch", instance_id]
        started_at = time.monotonic()
        last_log_size = log_path.stat().st_size if log_path.is_file() else 0
        last_log_change = started_at
        detected_markers: list[str] = []
        process_exit_code: int | None = None
        freeze_detected = False
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout, stderr_path.open("w", encoding="utf-8", errors="replace") as stderr:
            try:
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr, cwd=str(executable.parent))
            except OSError as exc:
                report = LaunchValidationReport(
                    status="failed",
                    stage="game_start",
                    summary=f"Failed to start Prism Launcher: {exc}",
                    log_path=str(log_path) if log_path.exists() else None,
                    seconds_observed=0,
                    output_dir=str(output_dir),
                    evidence_path=str(evidence_path),
                )
                _write_evidence(evidence_path, report, command=command, stdout_path=stdout_path, stderr_path=stderr_path)
                return report

            while time.monotonic() - started_at < wait_seconds:
                time.sleep(1)
                process_exit_code = process.poll()
                if log_path.is_file():
                    current_size = log_path.stat().st_size
                    if current_size != last_log_size:
                        last_log_size = current_size
                        last_log_change = time.monotonic()
                    markers = _detect_log_markers(log_path)
                    detected_markers = sorted(set(detected_markers) | set(markers))
                    crash = _newest_crash_report(instance_path)
                    if crash and crash != crash_before:
                        report = LaunchValidationReport(
                            status="failed",
                            stage=_stage_from_markers(detected_markers),
                            summary="Prism runtime crashed during launch-check.",
                            crash_report_path=str(crash),
                            log_path=str(log_path),
                            seconds_observed=int(time.monotonic() - started_at),
                            output_dir=str(output_dir),
                            evidence_path=str(evidence_path),
                            detected_markers=detected_markers,
                            process_exit_code=process_exit_code,
                        )
                        _terminate_process(process)
                        if validation_world and not keep_validation_world:
                            _cleanup_validation_world(instance_path)
                        _write_evidence(evidence_path, report, command=command, stdout_path=stdout_path, stderr_path=stderr_path)
                        return report
                    smoke_stable = smoke_test_mod_injected and "STABLE_60_SECONDS" in markers and "PLAYER_JOINED_WORLD" in markers
                    legacy_world_join = "world_join" in markers and not smoke_test_mod_injected
                    if smoke_stable or legacy_world_join:
                        report = LaunchValidationReport(
                            status="passed" if smoke_stable else "manual_required",
                            stage="complete",
                            summary=(
                                "Prism launch-check passed with MythWeaver smoke-test stability proof."
                                if smoke_stable
                                else "Prism observed broad world-join evidence, but no MythWeaver smoke-test stability proof."
                            ),
                            log_path=str(log_path),
                            seconds_observed=int(time.monotonic() - started_at),
                            output_dir=str(output_dir),
                            evidence_path=str(evidence_path),
                            detected_markers=detected_markers,
                            process_exit_code=process_exit_code,
                            smoke_test_mod_injected=smoke_test_mod_injected,
                            smoke_test_markers_seen=[marker for marker in detected_markers if marker.isupper()],
                            required_markers_met=smoke_stable,
                            stability_seconds_proven=120 if "STABLE_120_SECONDS" in markers else 60 if "STABLE_60_SECONDS" in markers else 0,
                            runtime_proof_observed=smoke_stable,
                        )
                        _terminate_process(process)
                        if validation_world and not keep_validation_world:
                            _cleanup_validation_world(instance_path)
                        _write_evidence(evidence_path, report, command=command, stdout_path=stdout_path, stderr_path=stderr_path)
                        return report
                if process_exit_code is not None:
                    break
                if time.monotonic() - last_log_change > max(30, min(wait_seconds, 90)):
                    freeze_detected = True
                    break

            if freeze_detected:
                _terminate_process(process)
            else:
                process_exit_code = process.poll()
            report = _analyze_existing_runtime_evidence(
                instance_path=instance_path,
                wait_seconds=int(time.monotonic() - started_at),
                output_dir=output_dir,
                process_exit_code=process_exit_code,
                freeze_detected=freeze_detected,
                summary_if_missing="Prism launch-check did not observe world-join proof before timeout.",
            )
            if report.status != "passed":
                _terminate_process(process)
            if validation_world and not keep_validation_world:
                _cleanup_validation_world(instance_path)
            report.evidence_path = str(evidence_path)
            _write_evidence(evidence_path, report, command=command, stdout_path=stdout_path, stderr_path=stderr_path)
            return report


def _prism_data_candidates(env: dict[str, str]) -> list[Path]:
    roots = [env.get("APPDATA"), env.get("LOCALAPPDATA"), env.get("USERPROFILE")]
    candidates: list[Path] = []
    configured_instances = env.get("MYTHWEAVER_PRISM_INSTANCES_PATH")
    if configured_instances:
        configured = Path(configured_instances)
        candidates.extend([configured, configured.parent if configured.name.lower() == "instances" else configured / "instances"])
    configured_root = env.get("MYTHWEAVER_PRISM_ROOT")
    if configured_root:
        candidates.extend([Path(configured_root), Path(configured_root) / "instances"])
    for root in roots:
        if root:
            base = Path(root)
            candidates.extend([base / "PrismLauncher", base / "PrismLauncher" / "instances", base / ".local" / "share" / "PrismLauncher"])
    return candidates


def _prism_executable_candidates(env: dict[str, str]) -> list[Path]:
    roots = [env.get("LOCALAPPDATA"), env.get("ProgramFiles"), env.get("ProgramFiles(x86)")]
    candidates: list[Path] = []
    configured = env.get("MYTHWEAVER_PRISM_EXECUTABLE_PATH") or env.get("MYTHWEAVER_PRISM_PATH")
    if configured:
        candidates.append(Path(configured))
    for root in roots:
        if root:
            base = Path(root)
            candidates.extend([
                base / "PrismLauncher.exe",
                base / "PrismLauncher" / "prismlauncher.exe",
                base / "PrismLauncher" / "PrismLauncher.exe",
                base / "Prism Launcher" / "prismlauncher.exe",
                base / "Prism Launcher" / "PrismLauncher.exe",
                base / "PrismLauncher" / "prismlauncher",
                base / "Prism Launcher" / "prismlauncher",
            ])
    return candidates


def _instance_id(name: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in name).strip("-") or "mythweaver-pack"


def _first_existing_executable(env: dict[str, str]) -> Path | None:
    for path in _prism_executable_candidates(env):
        if path.is_file():
            return path
    return None


def _first_existing_data_root(env: dict[str, str]) -> Path | None:
    configured = env.get("MYTHWEAVER_PRISM_INSTANCES_PATH")
    if configured:
        path = Path(configured)
        return path.parent if path.name.lower() == "instances" else path
    for path in _prism_data_candidates(env):
        if path.name.lower() == "instances" and path.is_dir():
            return path.parent
        if (path / "instances").is_dir():
            return path
    return None


def _latest_log_path(instance_path: Path) -> Path:
    return instance_path / ".minecraft" / "logs" / "latest.log"


def _resolve_registered_instance(instance_path: Path, env: dict[str, str]) -> tuple[Path, str] | None:
    try:
        resolved = Path(instance_path).resolve()
    except OSError:
        return None
    if not resolved.exists():
        return None
    for root in _prism_instances_roots(env):
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        if resolved.parent == root_resolved:
            return resolved, resolved.name
    return None


def _register_generated_instance_for_launch(instance_path: Path, env: dict[str, str]) -> tuple[Path, str] | None:
    source = Path(instance_path)
    if not _looks_like_prism_instance(source):
        return None
    roots = [root for root in _prism_instances_roots(env) if root.exists() or root.parent.exists()]
    if not roots:
        return None
    target_root = roots[0]
    instance_id = source.name
    target = target_root / instance_id
    try:
        if source.resolve() == target.resolve():
            return target, instance_id
    except OSError:
        return None
    try:
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
    except OSError:
        return None
    return target, instance_id


def _looks_like_prism_instance(path: Path) -> bool:
    return path.is_dir() and (path / "mmc-pack.json").is_file() and (path / "instance.cfg").is_file()


def resolve_registered_prism_instance(instance_path: Path, env: dict[str, str] | None = None) -> tuple[Path, str] | None:
    return _resolve_registered_instance(instance_path, env or dict(os.environ))


def _prism_instances_roots(env: dict[str, str]) -> list[Path]:
    roots: list[Path] = []
    configured = env.get("MYTHWEAVER_PRISM_INSTANCES_PATH")
    if configured:
        path = Path(configured)
        roots.append(path if path.name.lower() == "instances" else path / "instances")
    data_root = _first_existing_data_root(env)
    if data_root:
        roots.append(data_root / "instances")
    for candidate in _prism_data_candidates(env):
        roots.append(candidate if candidate.name.lower() == "instances" else candidate / "instances")
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            deduped.append(root)
    return deduped


def _newest_crash_report(instance_path: Path) -> Path | None:
    crash_dir = instance_path / ".minecraft" / "crash-reports"
    if not crash_dir.is_dir():
        return None
    reports = sorted(crash_dir.glob("*.txt"), key=lambda path: path.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def _detect_log_markers(log_path: Path) -> list[str]:
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
    for marker in (
        "CLIENT_READY",
        "SERVER_STARTING",
        "SERVER_STARTED",
        "PLAYER_JOINED_WORLD",
        "STABLE_30_SECONDS",
        "STABLE_60_SECONDS",
        "STABLE_120_SECONDS",
    ):
        if f"[MythWeaverSmokeTest] {marker}" in text or f"[mythweaversmoketest] {marker.lower()}" in text:
            markers.append(marker)
    return markers


def _stage_from_markers(markers: list[str]) -> str:
    if "PLAYER_JOINED_WORLD" in markers or "world_join" in markers:
        return "world_join"
    if "main_menu" in markers:
        return "main_menu"
    if "launcher_start" in markers:
        return "game_start"
    return "not_started"


def _analyze_existing_runtime_evidence(
    *,
    instance_path: Path,
    wait_seconds: int,
    output_dir: Path,
    process_exit_code: int | None,
    freeze_detected: bool,
    summary_if_missing: str,
) -> LaunchValidationReport:
    log_path = _latest_log_path(instance_path)
    crash = _newest_crash_report(instance_path)
    markers = _detect_log_markers(log_path)
    if process_exit_code is not None and process_exit_code != 0:
        return LaunchValidationReport(
            status="failed",
            stage=_stage_from_markers(markers),
            summary=f"Prism launch-check process exited nonzero with code {process_exit_code}.",
            crash_report_path=str(crash) if crash else None,
            log_path=str(log_path) if log_path.is_file() else None,
            seconds_observed=wait_seconds,
            output_dir=str(output_dir),
            detected_markers=markers,
            process_exit_code=process_exit_code,
            freeze_detected=freeze_detected,
        )
    if crash or "crash" in markers:
        return LaunchValidationReport(
            status="failed",
            stage=_stage_from_markers(markers),
            summary="Runtime crash evidence was found during launch-check.",
            crash_report_path=str(crash) if crash else None,
            log_path=str(log_path) if log_path.is_file() else None,
            seconds_observed=wait_seconds,
            output_dir=str(output_dir),
            detected_markers=markers,
            process_exit_code=process_exit_code,
            freeze_detected=freeze_detected,
        )
    smoke_stable = "PLAYER_JOINED_WORLD" in markers and "STABLE_60_SECONDS" in markers
    if smoke_stable:
        return LaunchValidationReport(
            status="passed",
            stage="complete",
            summary="Runtime smoke test passed with MythWeaver smoke-test stability proof.",
            log_path=str(log_path),
            seconds_observed=wait_seconds,
            output_dir=str(output_dir),
            detected_markers=markers,
            process_exit_code=process_exit_code,
            freeze_detected=freeze_detected,
            smoke_test_markers_seen=[marker for marker in markers if marker.isupper()],
            required_markers_met=True,
            stability_seconds_proven=120 if "STABLE_120_SECONDS" in markers else 60,
            runtime_proof_observed=True,
        )
    if "world_join" in markers:
        return LaunchValidationReport(
            status="manual_required",
            stage="world_join",
            summary="Runtime found broad world-join evidence, but MythWeaver smoke-test stability proof is missing.",
            log_path=str(log_path),
            seconds_observed=wait_seconds,
            output_dir=str(output_dir),
            detected_markers=markers,
            process_exit_code=process_exit_code,
            freeze_detected=freeze_detected,
        )
    status = "failed" if freeze_detected else "manual_required"
    summary = "Runtime appears frozen: latest.log stopped changing before world-join proof." if freeze_detected else summary_if_missing
    return LaunchValidationReport(
        status=status,
        stage=_stage_from_markers(markers),
        summary=summary,
        log_path=str(log_path) if log_path.is_file() else None,
        seconds_observed=wait_seconds,
        output_dir=str(output_dir),
        detected_markers=markers,
        process_exit_code=process_exit_code,
        freeze_detected=freeze_detected,
    )


def _write_evidence(
    evidence_path: Path,
    report: LaunchValidationReport,
    *,
    command: list[str] | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> None:
    payload = {
        "status": report.status,
        "stage": report.stage,
        "summary": report.summary,
        "seconds_observed": report.seconds_observed,
        "latest_log_path": report.log_path,
        "crash_report_path": report.crash_report_path,
        "detected_markers": report.detected_markers,
        "process_exit_code": report.process_exit_code,
        "freeze_detected": report.freeze_detected,
        "smoke_test_mod_injected": report.smoke_test_mod_injected,
        "smoke_test_markers_seen": report.smoke_test_markers_seen,
        "required_markers_met": report.required_markers_met,
        "stability_seconds_proven": report.stability_seconds_proven,
        "runtime_proof_observed": report.runtime_proof_observed,
        "validation_world_created": report.validation_world_created,
        "validation_world_cleaned": report.validation_world_cleaned,
        "validation_world_path": report.validation_world_path,
        "command": command,
        "prism_instance_id": command[-1] if command and "--launch" in command else None,
        "prism_registered_instance_path": _instance_path_from_log(report.log_path),
        "stdout_path": str(stdout_path) if stdout_path else None,
        "stderr_path": str(stderr_path) if stderr_path else None,
    }
    evidence_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _terminate_process(process: subprocess.Popen[str] | subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _cleanup_validation_world(instance_path: Path) -> None:
    saves = instance_path / ".minecraft" / "saves"
    for name in ("MythWeaver Runtime Smoke Test", "MythWeaverRuntimeSmokeTest"):
        target = saves / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)


def _instance_path_from_log(log_path: str | None) -> str | None:
    if not log_path:
        return None
    path = Path(log_path)
    try:
        return str(path.parents[2])
    except IndexError:
        return None
