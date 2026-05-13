from __future__ import annotations

from pathlib import Path

from mythweaver.launcher.runtime import (
    parse_smoke_test_markers,
    stability_seconds_from_markers,
)
from mythweaver.runtime.contracts import RuntimeProof, RuntimeProofLevel

REQUIRED_WORLD_MARKERS = {"CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD"}


def proof_from_runtime_text(
    text: str,
    *,
    latest_log_path: Path | None = None,
    smoke_test_mod_used: bool = False,
    evidence_path: str | None = None,
    minimum_stability_seconds: int = 60,
) -> RuntimeProof:
    markers = _markers_from_text(text)
    if latest_log_path is not None and latest_log_path.is_file():
        file_markers, _timestamps = parse_smoke_test_markers(latest_log_path)
        for marker in file_markers:
            if marker not in markers:
                markers.append(marker)
    stability = stability_seconds_from_markers(markers)
    required_met = _required_markers_met(markers, minimum_stability_seconds=minimum_stability_seconds)
    return RuntimeProof(
        proof_level=_proof_level(text, markers),
        runtime_proof_observed=required_met,
        smoke_test_mod_used=smoke_test_mod_used,
        smoke_test_markers_seen=markers,
        required_markers_met=required_met,
        stability_seconds_proven=stability,
        evidence_path=evidence_path,
        final_export_excluded_smoketest_mod=True,
    )


def proof_meets_requirement(proof: RuntimeProof | None, *, minimum_stability_seconds: int = 60) -> bool:
    if proof is None:
        return False
    return proof.required_markers_met and proof.stability_seconds_proven >= minimum_stability_seconds


def _markers_from_text(text: str) -> list[str]:
    markers: list[str] = []
    for line in text.splitlines():
        if "[MythWeaverSmokeTest]" not in line:
            continue
        for marker in (
            "CLIENT_READY",
            "SERVER_STARTING",
            "SERVER_STARTED",
            "PLAYER_JOINED_WORLD",
            "STABLE_30_SECONDS",
            "STABLE_60_SECONDS",
            "STABLE_120_SECONDS",
        ):
            if marker in line and marker not in markers:
                markers.append(marker)
    return markers


def _required_markers_met(markers: list[str], *, minimum_stability_seconds: int) -> bool:
    marker_set = set(markers)
    if not REQUIRED_WORLD_MARKERS.issubset(marker_set):
        return False
    return stability_seconds_from_markers(markers) >= minimum_stability_seconds


def _proof_level(text: str, markers: list[str]) -> RuntimeProofLevel:
    stability = stability_seconds_from_markers(markers)
    if stability >= 120:
        return "stable_120"
    if stability >= 60:
        return "stable_60"
    if stability >= 30:
        return "stable_30"
    if "PLAYER_JOINED_WORLD" in markers:
        return "world_joined"
    if "CLIENT_READY" in markers:
        return "client_initialized"
    lowered = text.lower()
    if any(term in lowered for term in ("sound engine started", "narrator library", "created: 1024x", "reloading resourcemanager")):
        return "main_menu_likely"
    if any(term in lowered for term in ("minecraft client initialized", "launching wrapped minecraft", "loading minecraft")):
        return "client_initialized"
    return "none"
