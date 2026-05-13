from __future__ import annotations

from mythweaver.autopilot.contracts import AutopilotBlocker
from mythweaver.runtime.contracts import RuntimeDiagnosis, RuntimeIssue, RuntimeProof


def blockers_from_runtime(
    *,
    reasons: list[str],
    issues: list[RuntimeIssue],
    diagnoses: list[RuntimeDiagnosis],
    proof: RuntimeProof | None,
    attempt_number: int | None,
) -> list[AutopilotBlocker]:
    blockers: list[AutopilotBlocker] = []
    for diagnosis in diagnoses:
        blocker = _blocker_for_kind(
            diagnosis.kind,
            message=diagnosis.summary,
            attempt_number=attempt_number,
            evidence_path=_evidence_path(proof),
            data={
                "diagnosis_kind": diagnosis.kind,
                "confidence": diagnosis.confidence,
                "affected_mod_ids": diagnosis.affected_mod_ids,
                "affected_files": diagnosis.affected_files,
            },
        )
        if blocker is not None:
            blockers.append(blocker)
    for issue in issues:
        blocker = _blocker_for_kind(
            issue.kind,
            message=issue.message,
            attempt_number=attempt_number,
            evidence_path=_evidence_path(proof),
            data={"issue_kind": issue.kind, "severity": issue.severity, "confidence": issue.confidence},
        )
        if blocker is not None:
            blockers.append(blocker)
    for reason in reasons:
        blockers.append(_blocker_for_reason(reason, attempt_number=attempt_number, evidence_path=_evidence_path(proof)))
    return _dedupe_blockers(blockers)


def blocker_for_source_policy(
    *,
    message: str,
    evidence: list[str],
    attempt_number: int | None,
) -> AutopilotBlocker:
    return AutopilotBlocker(
        kind="source_policy_blocked",
        message=message,
        severity="error",
        agent_can_retry=True,
        user_action_required=True,
        suggested_next_step="Inspect source/export blockers, change sources or target export, or ask the user for manual approval.",
        related_attempt=attempt_number,
        data={"evidence": evidence[:10]},
    )


def blocker_for_invalid_request(message: str) -> AutopilotBlocker:
    return AutopilotBlocker(
        kind="invalid_request",
        message=message,
        severity="fatal",
        agent_can_retry=True,
        user_action_required=True,
        suggested_next_step="Fix the request or selected_mods.json path and run Autopilot again.",
    )


def _blocker_for_kind(
    kind: str,
    *,
    message: str,
    attempt_number: int | None,
    evidence_path: str | None,
    data: dict[str, object],
) -> AutopilotBlocker | None:
    mapping = {
        "unsupported_loader_runtime": ("fatal", False, True, "Choose Fabric for private runtime V1 or export without private runtime validation."),
        "source_policy_blocked": ("error", True, True, "Change sources/target export or provide a trusted runtime-installable file."),
        "smoke_test_proof_missing": ("error", True, True, "Provide the smoke-test helper jar or disable strict proof with an explicit weaker-proof run."),
        "weak_runtime_proof": ("error", True, True, "Use strict smoke-test helper proof or inspect evidence before retrying."),
        "runtime_proof_missing": ("error", True, True, "Provide smoke-test proof or inspect runtime evidence."),
        "smoke_test_helper_missing": ("error", True, True, "Build or pass the MythWeaver smoke-test helper jar."),
        "java_runtime_missing": ("fatal", True, True, "Install or pass a compatible Java runtime path."),
        "java_version_mismatch": ("error", True, True, "Use a Java version compatible with the target Minecraft version."),
        "runtime_instance_prepare_failed": ("fatal", True, True, "Inspect runtime setup evidence and retry after fixing the environment."),
        "minecraft_client_prepare_failed": ("fatal", True, True, "Inspect Mojang/Fabric cache setup and retry when metadata is available."),
        "timeout": ("error", True, False, "Retry with a longer timeout or inspect runtime evidence for startup hangs."),
    }
    if kind not in mapping:
        return None
    severity, retry, user_required, next_step = mapping[kind]
    return AutopilotBlocker(
        kind=kind,
        message=message,
        severity=severity,  # type: ignore[arg-type]
        agent_can_retry=retry,
        user_action_required=user_required,
        suggested_next_step=next_step,
        related_attempt=attempt_number,
        evidence_path=evidence_path,
        data=data,
    )


def _blocker_for_reason(reason: str, *, attempt_number: int | None, evidence_path: str | None) -> AutopilotBlocker:
    lowered = reason.lower()
    if "max attempts" in lowered:
        kind = "max_attempts_reached"
        severity = "error"
        retry = True
        user_required = False
        next_step = "Review the attempts and evidence, then rerun with changed constraints if appropriate."
    elif "repeated issue" in lowered:
        kind = "repeated_failure"
        severity = "error"
        retry = False
        user_required = True
        next_step = "Inspect the repeated diagnosis before retrying to avoid an infinite repair loop."
    elif "dangerous" in lowered:
        kind = "dangerous_repair_blocked"
        severity = "fatal"
        retry = False
        user_required = True
        next_step = "Review the dangerous repair manually; Autopilot will not apply it."
    elif "manual" in lowered:
        kind = "manual_repair_required"
        severity = "error"
        retry = False
        user_required = True
        next_step = "Ask the user to approve or perform the manual repair."
    elif "runtime unsupported" in lowered:
        kind = "unsupported_loader_runtime"
        severity = "fatal"
        retry = True
        user_required = True
        next_step = "Switch to Fabric for private runtime V1 or stop runtime validation."
    else:
        kind = "no_safe_repair_available"
        severity = "error"
        retry = False
        user_required = True
        next_step = "Inspect diagnoses and evidence; no safe deterministic repair was available."
    return AutopilotBlocker(
        kind=kind,
        message=reason,
        severity=severity,  # type: ignore[arg-type]
        agent_can_retry=retry,
        user_action_required=user_required,
        suggested_next_step=next_step,
        related_attempt=attempt_number,
        evidence_path=evidence_path,
    )


def _evidence_path(proof: RuntimeProof | None) -> str | None:
    return proof.evidence_path if proof is not None else None


def _dedupe_blockers(blockers: list[AutopilotBlocker]) -> list[AutopilotBlocker]:
    seen: set[str] = set()
    output: list[AutopilotBlocker] = []
    for blocker in blockers:
        key = f"{blocker.kind}|{blocker.related_attempt}|{blocker.message}"
        if key in seen:
            continue
        seen.add(key)
        output.append(blocker)
    return output
