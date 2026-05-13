from __future__ import annotations

import re

from mythweaver.runtime.contracts import RuntimeIssue


def classify_runtime_text(text: str) -> list[RuntimeIssue]:
    lower = text.lower()
    issues: list[RuntimeIssue] = []
    if any(marker in lower for marker in ("modresolutionexception", "could not find required mod", "requires mod", "depends on")):
        missing = _missing_mods(text)
        issues.append(
            RuntimeIssue(
                kind="missing_dependency",
                severity="fatal",
                confidence=0.88,
                message=f"Missing required dependency: {', '.join(missing) if missing else 'unknown'}",
                evidence=_evidence(text, ["modresolutionexception", "required mod", "requires mod", "depends on"]),
                missing_mods=missing,
            )
        )
    if "unsupportedclassversionerror" in lower or "compiled by a more recent version of the java runtime" in lower or "class file version" in lower:
        issues.append(
            RuntimeIssue(
                kind="java_version_mismatch",
                severity="fatal",
                confidence=0.9,
                message="The selected Java runtime is too old for one or more classes.",
                evidence=_evidence(text, ["unsupportedclassversionerror", "compiled by", "class file version"]),
            )
        )
    if "duplicatemodsfoundexception" in lower or "duplicate mod" in lower:
        issues.append(
            RuntimeIssue(
                kind="duplicate_mod",
                severity="fatal",
                confidence=0.82,
                message="Duplicate mod files or mod ids were reported.",
                evidence=_evidence(text, ["duplicatemodsfoundexception", "duplicate mod"]),
            )
        )
    if "mixin apply failed" in lower or "injectionerror" in lower or "mixintransformererror" in lower or "invalidmixinexception" in lower:
        issues.append(
            RuntimeIssue(
                kind="mixin_failure",
                severity="fatal",
                confidence=0.78,
                message="A mixin failed during class transformation.",
                evidence=_evidence(text, ["mixin apply failed", "injectionerror", "mixintransformererror", "invalidmixinexception"]),
            )
        )
    if "attempted to load class net/minecraft/client" in lower or "invalid dist dedicated_server" in lower or "client-only" in lower or "server-only" in lower:
        issues.append(
            RuntimeIssue(
                kind="side_mismatch",
                severity="fatal",
                confidence=0.78,
                message="A client/server side mismatch was reported.",
                evidence=_evidence(text, ["attempted to load class", "invalid dist", "client-only", "server-only"]),
            )
        )
    if "zipexception" in lower or "invalid loc header" in lower or "error in opening zip file" in lower or "hash mismatch" in lower:
        issues.append(
            RuntimeIssue(
                kind="corrupt_or_invalid_jar",
                severity="fatal",
                confidence=0.86,
                message="A jar appears corrupt or failed validation.",
                evidence=_evidence(text, ["zipexception", "invalid loc", "opening zip", "hash mismatch"]),
            )
        )
    if "requires minecraft" in lower or "wrong minecraft version" in lower:
        issues.append(
            RuntimeIssue(
                kind="minecraft_version_mismatch",
                severity="fatal",
                confidence=0.78,
                message="A mod targets a different Minecraft version.",
                evidence=_evidence(text, ["requires minecraft", "wrong minecraft version"]),
            )
        )
    if "wrong loader" in lower or "requires fabric loader" in lower or "requires forge" in lower or "requires neoforge" in lower:
        issues.append(
            RuntimeIssue(
                kind="loader_mismatch",
                severity="fatal",
                confidence=0.76,
                message="A mod targets a different loader.",
                evidence=_evidence(text, ["wrong loader", "requires fabric", "requires forge", "requires neoforge"]),
            )
        )
    if "conflict" in lower and ("mod" in lower or "incompatible" in lower):
        issues.append(
            RuntimeIssue(
                kind="mod_conflict",
                severity="fatal",
                confidence=0.65,
                message="A mod conflict was reported.",
                evidence=_evidence(text, ["conflict", "incompatible"]),
            )
        )
    if not issues and text.strip():
        issues.append(
            RuntimeIssue(
                kind="unknown_launch_failure",
                severity="fatal",
                confidence=0.35,
                message="Runtime failed but did not match a deterministic classifier.",
                evidence=text.splitlines()[:5],
            )
        )
    return issues


def timeout_issue(timeout_seconds: int) -> RuntimeIssue:
    return RuntimeIssue(
        kind="timeout",
        severity="fatal",
        confidence=1.0,
        message=f"Minecraft did not reach a conservative success signal within {timeout_seconds} seconds.",
        evidence=[f"timeout_seconds={timeout_seconds}"],
    )


def unsupported_loader_issue(loader: str) -> RuntimeIssue:
    return RuntimeIssue(
        kind="unsupported_loader_runtime",
        severity="fatal",
        confidence=1.0,
        message=f"MythWeaver private runtime V1 does not support launching loader '{loader}'.",
        evidence=[f"loader={loader}", "supported_private_runtime_loaders=fabric"],
    )


def _evidence(text: str, needles: list[str]) -> list[str]:
    output: list[str] = []
    for line in text.splitlines():
        lower = line.lower()
        if any(needle in lower for needle in needles):
            output.append(line.strip())
        if len(output) >= 5:
            break
    return output or text.splitlines()[:3]


def _missing_mods(text: str) -> list[str]:
    candidates: list[str] = []
    patterns = [
        r"requires mod ['\"]?([a-zA-Z0-9_.-]+)",
        r"required mod ['\"]?([a-zA-Z0-9_.-]+)",
        r"depends on ['\"]?([a-zA-Z0-9_.-]+)",
        r"Could not find required mod:?\s*['\"]?([a-zA-Z0-9_.-]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1).strip(" .'\"")
            if value.lower() not in {"mod", "dependency", "install"} and value not in candidates:
                candidates.append(value)
    return candidates
