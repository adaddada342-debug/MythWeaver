from __future__ import annotations

import subprocess
from pathlib import Path

from mythweaver.core.settings import Settings
from mythweaver.schemas.contracts import ValidationReport
from mythweaver.validation.crash_analyzer import analyze_failure


def _latest_log(instance_path: Path) -> Path | None:
    candidates = [
        instance_path / ".minecraft" / "logs" / "latest.log",
        instance_path / "minecraft" / "logs" / "latest.log",
        instance_path / "logs" / "latest.log",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    crash_dir = instance_path / ".minecraft" / "crash-reports"
    if crash_dir.is_dir():
        reports = sorted(crash_dir.glob("*.txt"), key=lambda path: path.stat().st_mtime, reverse=True)
        if reports:
            return reports[0]
    return None


def validate_launch(instance_id: str, settings: Settings, timeout_seconds: int = 300) -> ValidationReport:
    """Launch an instance through Prism when configured, otherwise return a clean skip."""

    prism_path_value = getattr(settings, "resolved_prism_path", None) or settings.prism_path
    prism_root_value = getattr(settings, "resolved_prism_root", None) or settings.prism_root
    prism_profile = getattr(settings, "resolved_prism_profile", None) or settings.prism_profile
    timeout_seconds = getattr(settings, "launch_timeout_seconds", timeout_seconds)

    if not prism_path_value or not prism_root_value:
        return ValidationReport(
            status="skipped",
            details="Prism launch validation skipped because Prism path/root is not configured.",
        )

    prism_path = Path(prism_path_value)
    prism_root = Path(prism_root_value)
    if not prism_path.exists():
        return ValidationReport(status="skipped", details=f"Prism executable not found: {prism_path}")

    command = [
        str(prism_path),
        "--dir",
        str(prism_root),
        "--launch",
        instance_id,
    ]
    if prism_profile:
        command.extend(["--profile", prism_profile])

    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return ValidationReport(
            status="timeout",
            launched=True,
            details=f"Prism launch timed out after {timeout_seconds} seconds.",
            analysis=analyze_failure((exc.stdout or "") + "\n" + (exc.stderr or "")),
            likely_causes=["timeout"],
            suggested_actions=["Increase launch timeout or inspect Prism launcher logs."],
        )

    instance_path = prism_root / "instances" / instance_id
    log_path = _latest_log(instance_path)
    log_text = ""
    if log_path:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    combined = "\n".join([completed.stdout, completed.stderr, log_text])
    if completed.returncode == 0:
        return ValidationReport(
            status="passed",
            launched=True,
            instance_path=str(instance_path),
            log_path=str(log_path) if log_path else None,
            details="Prism launch exited successfully.",
            logs_collected=[str(log_path)] if log_path else [],
            confidence=0.9,
            raw_summary="Prism exited with code 0.",
        )
    analysis = analyze_failure(combined)
    return ValidationReport(
        status="failed",
        launched=True,
        instance_path=str(instance_path),
        log_path=str(log_path) if log_path else None,
        details=f"Prism launch failed with exit code {completed.returncode}.",
        analysis=analysis,
        logs_collected=[str(log_path)] if log_path else [],
        likely_causes=[analysis.classification],
        suggested_actions=analysis.repair_candidates,
        raw_summary=analysis.summary,
        confidence=0.7,
    )
