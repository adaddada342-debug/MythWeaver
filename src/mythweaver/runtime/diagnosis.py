from __future__ import annotations

import re

from mythweaver.runtime.contracts import RuntimeDiagnosis, RuntimeIssue


def diagnose_runtime_failure(text: str, *, evidence_paths: list[str] | None = None) -> list[RuntimeDiagnosis]:
    evidence_paths = evidence_paths or []
    lowered = text.lower()
    diagnoses: list[RuntimeDiagnosis] = []
    if "---- minecraft crash report ----" in lowered or evidence_paths:
        diagnoses.append(
            RuntimeDiagnosis(
                kind="crash_report",
                confidence="high" if "---- minecraft crash report ----" in lowered else "medium",
                summary="Crash report evidence was present for this runtime failure.",
                evidence=_evidence(text, ["---- minecraft crash report ----"]) + evidence_paths,
                blocking=True,
                suggested_repair_action_kinds=["manual_review"],
            )
        )
    diagnosis = _first_matching_diagnosis(text, lowered)
    if diagnosis is not None:
        diagnoses.append(diagnosis)
    if not diagnoses:
        diagnoses.append(RuntimeDiagnosis(
            kind="unknown_launch_failure",
            confidence="low",
            summary="Runtime failed, but MythWeaver did not match a deterministic known failure pattern.",
            evidence=_evidence(text, []),
            blocking=True,
        ))
    return _dedupe_diagnoses(diagnoses)


def diagnoses_from_issues(issues: list[RuntimeIssue]) -> list[RuntimeDiagnosis]:
    diagnoses: list[RuntimeDiagnosis] = []
    for issue in issues:
        text = "\n".join([issue.message, *issue.evidence])
        if issue.kind == "unsupported_loader_runtime":
            diagnoses.append(
                RuntimeDiagnosis(
                    kind="unsupported_loader_runtime",
                    confidence="high",
                    summary=issue.message,
                    evidence=issue.evidence,
                    blocking=True,
                    suggested_repair_action_kinds=["manual_review"],
                )
            )
        elif issue.kind == "timeout":
            diagnoses.append(
                RuntimeDiagnosis(
                    kind="timeout",
                    confidence="high",
                    summary=issue.message,
                    evidence=issue.evidence,
                    blocking=True,
                    suggested_repair_action_kinds=["manual_review"],
                )
            )
        elif issue.kind in {"runtime_proof_missing", "smoke_test_helper_missing", "smoke_test_helper_injection_failed"}:
            diagnoses.append(
                RuntimeDiagnosis(
                    kind="smoke_test_proof_missing",
                    confidence="high",
                    summary=issue.message,
                    evidence=issue.evidence,
                    blocking=True,
                    suggested_repair_action_kinds=["manual_review"],
                )
            )
        elif issue.kind == "runtime_proof_insufficient":
            diagnoses.append(
                RuntimeDiagnosis(
                    kind="weak_runtime_proof",
                    confidence="high",
                    summary=issue.message,
                    evidence=issue.evidence,
                    blocking=True,
                    suggested_repair_action_kinds=["manual_review"],
                )
            )
        elif issue.kind == "java_version_mismatch":
            diagnoses.append(
                RuntimeDiagnosis(
                    kind="java_version_mismatch",
                    confidence="high",
                    summary=issue.message,
                    evidence=issue.evidence,
                    blocking=True,
                    suggested_repair_action_kinds=["change_java"],
                )
            )
        elif issue.kind == "missing_dependency":
            missing = issue.missing_mods
            if "fabric-api" in missing:
                diagnoses.append(_missing_fabric_api(text))
            elif missing:
                diagnoses.append(_missing_dependency(text, missing))
            else:
                diagnoses.extend(diagnose_runtime_failure(text))
        else:
            diagnoses.extend(diagnose_runtime_failure(text))
    return _dedupe_diagnoses(diagnoses)


def _first_matching_diagnosis(text: str, lowered: str) -> RuntimeDiagnosis | None:
    if "fabric-api" in lowered or "fabric api" in lowered:
        if any(term in lowered for term in ("requires mod", "required mod", "could not find required mod", "modresolutionexception", "noclassdeffounderror")):
            return RuntimeDiagnosis(
                kind="missing_fabric_api",
                confidence="high",
                summary="Fabric API appears to be missing from the runtime instance.",
                evidence=_evidence(text, ["fabric-api", "fabric api", "requires mod", "noclassdeffounderror"]),
                blocking=True,
                affected_mod_ids=["fabric-api"],
                suggested_repair_action_kinds=["add_mod"],
            )
    if any(term in lowered for term in ("requires forge", "forge but fabric", "requires neoforge", "requires quilt")):
        loader = "forge" if "forge" in lowered else "neoforge" if "neoforge" in lowered else "quilt"
        return RuntimeDiagnosis(
            kind="loader_mismatch",
            confidence="high",
            summary=f"A mod appears to require {loader}, which is not the active private runtime loader.",
            evidence=_evidence(text, ["requires forge", "requires neoforge", "requires quilt", "fabric loader"]),
            blocking=True,
            affected_mod_ids=_mod_ids(text),
            suggested_repair_action_kinds=["manual_review"],
        )
    if "unsupportedclassversionerror" in lowered or "compiled by a more recent version of the java runtime" in lowered or "class file version" in lowered:
            return RuntimeDiagnosis(
            kind="java_version_mismatch",
            confidence="high",
            summary="The selected Java runtime is incompatible with one or more compiled classes.",
            evidence=_evidence(text, ["unsupportedclassversionerror", "compiled by", "class file version"]),
            blocking=True,
            suggested_repair_action_kinds=["change_java"],
        )
    if "mixin apply failed" in lowered or "injectionerror" in lowered or "mixintransformererror" in lowered or "invalidmixinexception" in lowered:
        return RuntimeDiagnosis(
            kind="mixin_failure",
            confidence="high",
            summary="A mixin failed during class transformation.",
            evidence=_evidence(text, ["mixin apply failed", "injectionerror", "mixintransformererror", "invalidmixinexception"]),
            blocking=True,
            affected_mod_ids=_mod_ids(text),
            suggested_repair_action_kinds=["manual_review"],
        )
    if "duplicatemodsfoundexception" in lowered or "duplicate mod id" in lowered or "duplicate mod" in lowered:
        mods = _mod_ids(text)
        return RuntimeDiagnosis(
            kind="duplicate_mod" if mods else "mod_id_conflict",
            confidence="high" if mods else "medium",
            summary="Duplicate mod files or duplicate mod ids were reported.",
            evidence=_evidence(text, ["duplicatemodsfoundexception", "duplicate mod id", "duplicate mod"]),
            blocking=True,
            affected_mod_ids=mods,
            suggested_repair_action_kinds=["remove_mod"] if mods else ["manual_review"],
        )
    if any(term in lowered for term in ("failed loading config", "failed to load config", "parsingexception", "tomlparseerror", "jsonparseexception")):
        return RuntimeDiagnosis(
            kind="config_parse_error",
            confidence="high",
            summary="A config file failed to parse during runtime startup.",
            evidence=_evidence(text, ["failed loading config", "failed to load config", "parsingexception", "tomlparseerror", "jsonparseexception"]),
            blocking=True,
            affected_files=_files(text),
            suggested_repair_action_kinds=["manual_review"],
        )
    if "accesswidener" in lowered or "access widener" in lowered:
        return RuntimeDiagnosis(
            kind="access_widener_failure",
            confidence="high",
            summary="An access widener failed to load or parse.",
            evidence=_evidence(text, ["accesswidener", "access widener"]),
            blocking=True,
            affected_files=_files(text),
            suggested_repair_action_kinds=["manual_review"],
        )
    if "nosuchmethoderror" in lowered:
        return RuntimeDiagnosis(
            kind="no_such_method_error",
            confidence="high",
            summary="A binary compatibility error was reported: a method expected by a mod is missing.",
            evidence=_evidence(text, ["nosuchmethoderror"]),
            blocking=True,
            affected_mod_ids=_mod_ids(text),
            suggested_repair_action_kinds=["manual_review"],
        )
    if "classnotfoundexception" in lowered or "noclassdeffounderror" in lowered:
        return RuntimeDiagnosis(
            kind="class_not_found",
            confidence="high",
            summary="A required class was missing at runtime.",
            evidence=_evidence(text, ["classnotfoundexception", "noclassdeffounderror"]),
            blocking=True,
            affected_mod_ids=_mod_ids(text),
            suggested_repair_action_kinds=["manual_review"],
        )
    if "invalid dist dedicated_server" in lowered or "attempted to load class net/minecraft/client" in lowered:
        return RuntimeDiagnosis(
            kind="client_only_mod_on_server",
            confidence="high",
            summary="A client-only class or mod was loaded in a server-side environment.",
            evidence=_evidence(text, ["invalid dist", "net/minecraft/client", "dedicated_server"]),
            blocking=True,
            affected_mod_ids=_mod_ids(text),
            suggested_repair_action_kinds=["manual_review"],
        )
    if "server-only" in lowered and "client" in lowered:
        return RuntimeDiagnosis(
            kind="server_only_mod_on_client",
            confidence="high",
            summary="A server-only mod appears to have loaded in the client runtime.",
            evidence=_evidence(text, ["server-only", "client environment"]),
            blocking=True,
            affected_mod_ids=_mod_ids(text),
            suggested_repair_action_kinds=["manual_review"],
        )
    if "wrong minecraft version" in lowered or "requires minecraft" in lowered:
        return RuntimeDiagnosis(
            kind="minecraft_version_mismatch",
            confidence="high",
            summary="A mod targets a different Minecraft version.",
            evidence=_evidence(text, ["wrong minecraft version", "requires minecraft"]),
            blocking=True,
            affected_mod_ids=_mod_ids(text),
            suggested_repair_action_kinds=["rerun_target_matrix"],
        )
    if "requires fabric loader" in lowered or "fabric loader version" in lowered:
        return RuntimeDiagnosis(
            kind="loader_mismatch",
            confidence="medium",
            summary="A mod requires a different Fabric loader version.",
            evidence=_evidence(text, ["requires fabric loader", "fabric loader version"]),
            blocking=True,
            affected_mod_ids=_mod_ids(text),
            suggested_repair_action_kinds=["update_loader"],
        )
    if any(term in lowered for term in ("unsupported mod environment", "not compatible with this environment")):
        return RuntimeDiagnosis(
            kind="unsupported_loader_runtime",
            confidence="high",
            summary="A mod reported that the active runtime environment is unsupported.",
            evidence=_evidence(text, ["unsupported mod environment", "not compatible"]),
            blocking=True,
            affected_mod_ids=_mod_ids(text),
            suggested_repair_action_kinds=["manual_review"],
        )
    missing = _missing_mods(text)
    if missing:
        return RuntimeDiagnosis(
            kind="missing_dependency",
            confidence="high",
            summary=f"Runtime reported missing required mod dependency: {', '.join(missing)}.",
            evidence=_evidence(text, ["requires mod", "required mod", "could not find required mod", "depends on", "modresolutionexception"]),
            blocking=True,
            affected_mod_ids=missing,
            suggested_repair_action_kinds=["add_mod"],
        )
    return None


def _missing_fabric_api(text: str) -> RuntimeDiagnosis:
    return RuntimeDiagnosis(
        kind="missing_fabric_api",
        confidence="high",
        summary="Fabric API appears to be missing from the runtime instance.",
        evidence=_evidence(text, ["fabric-api", "fabric api", "requires mod", "noclassdeffounderror"]),
        blocking=True,
        affected_mod_ids=["fabric-api"],
        suggested_repair_action_kinds=["add_mod"],
    )


def _missing_dependency(text: str, missing: list[str]) -> RuntimeDiagnosis:
    return RuntimeDiagnosis(
        kind="missing_dependency",
        confidence="high",
        summary=f"Runtime reported missing required mod dependency: {', '.join(missing)}.",
        evidence=_evidence(text, ["requires mod", "required mod", "could not find required mod", "depends on", "modresolutionexception"]),
        blocking=True,
        affected_mod_ids=missing,
        suggested_repair_action_kinds=["add_mod"],
    )


def _dedupe_diagnoses(diagnoses: list[RuntimeDiagnosis]) -> list[RuntimeDiagnosis]:
    seen: set[str] = set()
    output: list[RuntimeDiagnosis] = []
    for diagnosis in diagnoses:
        key = f"{diagnosis.kind}|{','.join(diagnosis.affected_mod_ids)}|{','.join(diagnosis.affected_files)}"
        if key in seen:
            continue
        seen.add(key)
        output.append(diagnosis)
    return output


def _missing_mods(text: str) -> list[str]:
    candidates: list[str] = []
    patterns = [
        r"requires mod ['\"]?([a-zA-Z0-9_.-]+)",
        r"required mod:?\s*['\"]?([a-zA-Z0-9_.-]+)",
        r"could not find required mod:?\s*['\"]?([a-zA-Z0-9_.-]+)",
        r"depends on ['\"]?([a-zA-Z0-9_.-]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1).strip(" .'\"")
            if value.lower() not in {"mod", "dependency", "install"} and value not in candidates:
                candidates.append(value)
    return candidates


def _mod_ids(text: str) -> list[str]:
    candidates = _missing_mods(text)
    patterns = [
        r"duplicate mod id ['\"]?([a-zA-Z0-9_.-]+)",
        r"mod id ['\"]?([a-zA-Z0-9_.-]+)",
        r"mod ['\"]?([a-zA-Z0-9_.-]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1).strip(" .'\":")
            if value.lower() not in {"id", "requires", "forge", "fabric", "client", "server"} and value not in candidates:
                candidates.append(value)
    return candidates[:5]


def _files(text: str) -> list[str]:
    output: list[str] = []
    for match in re.finditer(r"([A-Za-z0-9_.-]+\.(?:toml|json|json5|cfg|properties|jar|accesswidener))", text, flags=re.IGNORECASE):
        value = match.group(1)
        if value not in output:
            output.append(value)
    return output[:5]


def _evidence(text: str, needles: list[str]) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if needles:
        matched = [line for line in lines if any(needle in line.lower() for needle in needles)]
        if matched:
            return matched[:5]
    return lines[:5]
