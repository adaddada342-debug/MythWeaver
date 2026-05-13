from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Protocol, cast

from pydantic import Field

from mythweaver.runtime.classifiers import classify_runtime_text, timeout_issue
from mythweaver.runtime.contracts import RuntimeIssue, RuntimeProof
from mythweaver.runtime.proof import proof_from_runtime_text, proof_meets_requirement
from mythweaver.schemas.contracts import AgentSafeModel


class ProcessLike(Protocol):
    returncode: int | None

    def communicate(self, timeout: int | None = None) -> Any: ...

    def kill(self) -> None: ...

    def wait(self, timeout: int | None = None) -> Any: ...


class MonitorResult(AgentSafeModel):
    status: str
    exit_code: int | None = None
    success_signal: str | None = None
    issues: list[RuntimeIssue] = Field(default_factory=list)
    logs_scanned: list[str] = Field(default_factory=list)
    output_text: str = ""
    proof: RuntimeProof | None = None
    evidence_path: str | None = None


def monitor_command(
    command: list[str],
    *,
    instance_path: Path,
    timeout_seconds: int,
    success_grace_seconds: int,
    stop_after_success: bool = True,
    require_smoke_test_proof: bool = True,
    minimum_stability_seconds: int = 60,
    smoke_test_mod_used: bool = False,
    evidence_dir: Path | None = None,
    poll_interval_seconds: float = 0.1,
    process_factory: Callable[[list[str]], ProcessLike] | None = None,
) -> MonitorResult:
    del success_grace_seconds
    process_factory = process_factory or _popen
    process = process_factory(command)
    instance_path = Path(instance_path)
    evidence_dir = evidence_dir or instance_path
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "runtime_evidence.txt"
    stopped_after_success = False
    started = time.monotonic()

    if not callable(getattr(process, "poll", None)):
        return _communicate_and_classify(
            process,
            instance_path=instance_path,
            timeout_seconds=timeout_seconds,
            require_smoke_test_proof=require_smoke_test_proof,
            minimum_stability_seconds=minimum_stability_seconds,
            smoke_test_mod_used=smoke_test_mod_used,
            evidence_path=evidence_path,
        )

    last_text = ""
    while True:
        latest_log_path = _latest_log_path(instance_path)
        last_text = _bounded_text(_read_runtime_logs(instance_path))
        issues = _fatal_issues(last_text)
        if issues:
            _kill_process(process)
            return _result(
                status="failed",
                process=process,
                text=last_text,
                instance_path=instance_path,
                issues=issues,
                smoke_test_mod_used=smoke_test_mod_used,
                evidence_path=evidence_path,
                minimum_stability_seconds=minimum_stability_seconds,
            )
        proof = proof_from_runtime_text(
            last_text,
            latest_log_path=latest_log_path,
            smoke_test_mod_used=smoke_test_mod_used,
            evidence_path=str(evidence_path),
            minimum_stability_seconds=minimum_stability_seconds,
        )
        if proof_meets_requirement(proof, minimum_stability_seconds=minimum_stability_seconds) and stop_after_success:
            stopped_after_success = True
            _kill_process(process)
            break
        if cast(Any, process).poll() is not None:
            break
        if time.monotonic() - started >= timeout_seconds:
            _kill_process(process)
            try:
                process.wait(timeout=5)
            except Exception:
                pass
            proof = proof_from_runtime_text(
                last_text,
                latest_log_path=latest_log_path,
                smoke_test_mod_used=smoke_test_mod_used,
                evidence_path=str(evidence_path),
                minimum_stability_seconds=minimum_stability_seconds,
            )
            _write_evidence(evidence_path, last_text)
            return MonitorResult(
                status="timed_out",
                exit_code=process.returncode,
                issues=[timeout_issue(timeout_seconds)],
                logs_scanned=_logs_scanned(instance_path),
                output_text=last_text,
                proof=proof,
                evidence_path=str(evidence_path),
            )
        time.sleep(poll_interval_seconds)

    try:
        stdout, stderr = process.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        stdout, stderr = "", ""
    text = _bounded_text(f"{stdout or ''}\n{stderr or ''}\n{last_text}\n{_read_runtime_logs(instance_path)}")
    return _classify_completed(
        process,
        instance_path=instance_path,
        text=text,
        require_smoke_test_proof=require_smoke_test_proof,
        minimum_stability_seconds=minimum_stability_seconds,
        smoke_test_mod_used=smoke_test_mod_used,
        evidence_path=evidence_path,
        stopped_after_success=stopped_after_success,
    )


def _popen(command: list[str]) -> ProcessLike:
    kwargs: dict[str, Any] = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True, "shell": False}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    return cast(ProcessLike, subprocess.Popen(command, **kwargs))


def _communicate_and_classify(
    process: ProcessLike,
    *,
    instance_path: Path,
    timeout_seconds: int,
    require_smoke_test_proof: bool,
    minimum_stability_seconds: int,
    smoke_test_mod_used: bool,
    evidence_path: Path,
) -> MonitorResult:
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _kill_process(process)
        try:
            process.wait(timeout=5)
        except Exception:
            pass
        text = _bounded_text(_read_runtime_logs(instance_path))
        proof = proof_from_runtime_text(
            text,
            latest_log_path=_latest_log_path(instance_path),
            smoke_test_mod_used=smoke_test_mod_used,
            evidence_path=str(evidence_path),
            minimum_stability_seconds=minimum_stability_seconds,
        )
        _write_evidence(evidence_path, text)
        return MonitorResult(
            status="timed_out",
            exit_code=process.returncode,
            issues=[timeout_issue(timeout_seconds)],
            logs_scanned=_logs_scanned(instance_path),
            output_text=text,
            proof=proof,
            evidence_path=str(evidence_path),
        )
    text = _bounded_text(f"{stdout or ''}\n{stderr or ''}\n{_read_runtime_logs(instance_path)}")
    return _classify_completed(
        process,
        instance_path=instance_path,
        text=text,
        require_smoke_test_proof=require_smoke_test_proof,
        minimum_stability_seconds=minimum_stability_seconds,
        smoke_test_mod_used=smoke_test_mod_used,
        evidence_path=evidence_path,
        stopped_after_success=False,
    )


def _classify_completed(
    process: ProcessLike,
    *,
    instance_path: Path,
    text: str,
    require_smoke_test_proof: bool,
    minimum_stability_seconds: int,
    smoke_test_mod_used: bool,
    evidence_path: Path,
    stopped_after_success: bool,
) -> MonitorResult:
    proof = proof_from_runtime_text(
        text,
        latest_log_path=_latest_log_path(instance_path),
        smoke_test_mod_used=smoke_test_mod_used,
        evidence_path=str(evidence_path),
        minimum_stability_seconds=minimum_stability_seconds,
    )
    _write_evidence(evidence_path, text)
    issues = _fatal_issues(text)
    if issues:
        return _result(
            status="failed",
            process=process,
            text=text,
            instance_path=instance_path,
            issues=issues,
            smoke_test_mod_used=smoke_test_mod_used,
            evidence_path=evidence_path,
            minimum_stability_seconds=minimum_stability_seconds,
        )
    if process.returncode not in {0, None} and not stopped_after_success:
        return _result(
            status="failed",
            process=process,
            text=text,
            instance_path=instance_path,
            issues=classify_runtime_text(text),
            smoke_test_mod_used=smoke_test_mod_used,
            evidence_path=evidence_path,
            minimum_stability_seconds=minimum_stability_seconds,
        )
    proof_ok = proof_meets_requirement(proof, minimum_stability_seconds=minimum_stability_seconds)
    if proof_ok:
        return MonitorResult(
            status="passed",
            exit_code=process.returncode,
            success_signal=f"MythWeaver smoke-test proof: {proof.proof_level}",
            logs_scanned=_logs_scanned(instance_path),
            output_text=text,
            proof=proof,
            evidence_path=str(evidence_path),
        )
    if not require_smoke_test_proof:
        signal = _success_signal(text)
        if signal and process.returncode in {0, None}:
            return MonitorResult(
                status="passed",
                exit_code=process.returncode,
                success_signal=f"Weak runtime signal: {signal}",
                logs_scanned=_logs_scanned(instance_path),
                output_text=text,
                proof=proof,
                evidence_path=str(evidence_path),
            )
    proof_issue = RuntimeIssue(
        kind="runtime_proof_missing",
        severity="fatal" if require_smoke_test_proof else "warning",
        confidence=0.95,
        message="Required MythWeaver smoke-test world-join and stability proof was not observed.",
        evidence=proof.smoke_test_markers_seen or [_success_signal(text) or "no MythWeaver smoke-test markers"],
    )
    return MonitorResult(
        status="failed",
        exit_code=process.returncode,
        issues=[proof_issue],
        logs_scanned=_logs_scanned(instance_path),
        output_text=text,
        proof=proof,
        evidence_path=str(evidence_path),
    )


def _result(
    *,
    status: str,
    process: ProcessLike,
    text: str,
    instance_path: Path,
    issues: list[RuntimeIssue],
    smoke_test_mod_used: bool,
    evidence_path: Path,
    minimum_stability_seconds: int,
) -> MonitorResult:
    proof = proof_from_runtime_text(
        text,
        latest_log_path=_latest_log_path(instance_path),
        smoke_test_mod_used=smoke_test_mod_used,
        evidence_path=str(evidence_path),
        minimum_stability_seconds=minimum_stability_seconds,
    )
    _write_evidence(evidence_path, text)
    return MonitorResult(
        status=status,
        exit_code=process.returncode,
        issues=issues,
        logs_scanned=_logs_scanned(instance_path),
        output_text=text,
        proof=proof,
        evidence_path=str(evidence_path),
    )


def _fatal_issues(text: str) -> list[RuntimeIssue]:
    lowered = text.lower()
    if any(term in lowered for term in ("---- minecraft crash report ----", "reported exception", "exception in thread", "caught previously unhandled exception")):
        return [
            RuntimeIssue(
                kind="unknown_launch_failure",
                severity="fatal",
                confidence=0.8,
                message="Minecraft crash evidence was found in runtime logs or crash reports.",
                evidence=[line for line in text.splitlines() if "crash report" in line.lower() or "exception in thread" in line.lower()][:5],
            )
        ]
    return [issue for issue in classify_runtime_text(text) if issue.kind != "unknown_launch_failure"]


def _kill_process(process: ProcessLike) -> None:
    pid = getattr(process, "pid", None)
    if isinstance(pid, int):
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                return
            except Exception:
                pass
        else:
            try:
                killpg = getattr(os, "killpg", None)
                if callable(killpg):
                    killpg(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
                    return
            except Exception:
                pass
    try:
        process.kill()
    except Exception:
        pass


def _latest_log_path(instance_path: Path) -> Path | None:
    path = instance_path / ".minecraft" / "logs" / "latest.log"
    if path.is_file():
        return path
    path = instance_path / "logs" / "latest.log"
    return path if path.is_file() else None


def _read_latest_log(instance_path: Path) -> str:
    path = instance_path / ".minecraft" / "logs" / "latest.log"
    if not path.is_file():
        path = instance_path / "logs" / "latest.log"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_runtime_logs(instance_path: Path) -> str:
    pieces = [_read_latest_log(instance_path)]
    for directory in (instance_path / ".minecraft" / "crash-reports", instance_path / "crash-reports"):
        for path in sorted(directory.glob("*.txt")):
            if path.is_file():
                pieces.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(pieces)


def _logs_scanned(instance_path: Path) -> list[str]:
    output = []
    for directory, pattern in (
        (instance_path / ".minecraft" / "logs", "*.log"),
        (instance_path / "logs", "*.log"),
        (instance_path / ".minecraft" / "crash-reports", "*.txt"),
    ):
        for path in directory.glob(pattern):
            if path.is_file():
                output.append(str(path))
    latest = instance_path / ".minecraft" / "logs" / "latest.log"
    if latest.is_file() and str(latest) not in output:
        output.append(str(latest))
    return output


def _success_signal(text: str) -> str | None:
    for marker in ("Minecraft client initialized", "Sound engine started", "Created: 1024x", "Narrator library"):
        if marker.lower() in text.lower():
            return marker
    return None


def _bounded_text(text: str, limit: int = 200_000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _write_evidence(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_bounded_text(text), encoding="utf-8")
