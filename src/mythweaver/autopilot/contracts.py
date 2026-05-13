from __future__ import annotations

from typing import Literal

from pydantic import Field

from mythweaver.runtime.contracts import RuntimeAction, RuntimeDiagnosis, RuntimeIssue, RuntimeProof
from mythweaver.schemas.contracts import AgentSafeModel


class AutopilotRequest(AgentSafeModel):
    selected_mods_path: str
    sources: list[str]
    target_export: str = "local_instance"
    minecraft_version: str = "auto"
    loader: str = "auto"
    loader_version: str | None = None
    candidate_versions: list[str] = Field(default_factory=list)
    candidate_loaders: list[str] = Field(default_factory=list)
    max_attempts: int = 5
    memory_mb: int = 4096
    timeout_seconds: int = 180
    output_root: str | None = None
    java_path: str | None = None
    allow_manual_sources: bool = False
    allow_target_switch: bool = True
    allow_loader_switch: bool = True
    allow_minecraft_version_switch: bool = True
    allow_remove_content_mods: bool = False
    stop_on_manual_required: bool = True
    keep_failed_instances: bool = False
    inject_smoke_test: bool = True
    smoke_test_helper_path: str | None = None
    require_smoke_test_proof: bool = True
    minimum_stability_seconds: int = 60


class AutopilotAppliedAction(AgentSafeModel):
    action: RuntimeAction
    status: Literal["applied", "skipped", "blocked", "failed"]
    reason: str
    changed_selection: bool = False
    changed_target: bool = False


class AutopilotAttempt(AgentSafeModel):
    attempt_number: int
    minecraft_version: str
    loader: str
    loader_version: str | None
    build_status: str
    runtime_status: str
    issues: list[RuntimeIssue]
    actions_planned: list[RuntimeAction]
    actions_applied: list[AutopilotAppliedAction]
    blocked_reasons: list[str]
    instance_path: str | None
    proof: RuntimeProof | None = None
    diagnoses: list[RuntimeDiagnosis] = Field(default_factory=list)


class AutopilotReport(AgentSafeModel):
    status: Literal["verified_playable", "blocked", "max_attempts_reached", "failed"]
    final_minecraft_version: str | None
    final_loader: str | None
    final_loader_version: str | None
    attempts: list[AutopilotAttempt]
    final_instance_path: str | None
    final_export_path: str | None
    summary: str
    warnings: list[str]
    final_proof: RuntimeProof | None = None
    report_paths: dict[str, str] = Field(default_factory=dict)
