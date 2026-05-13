from __future__ import annotations

from typing import Literal

from pydantic import Field

from mythweaver.schemas.contracts import AgentSafeModel

RuntimeIssueSeverity = Literal["info", "warning", "error", "fatal"]
RuntimeActionKind = Literal[
    "add_mod",
    "replace_mod",
    "remove_mod",
    "update_loader",
    "change_java",
    "rerun_target_matrix",
    "manual_review",
]
RuntimeActionSafety = Literal["safe", "manual", "dangerous"]
RuntimeLaunchStatus = Literal["passed", "failed", "timed_out", "not_run"]
RuntimeLaunchStage = Literal["prepare", "download_minecraft", "install_loader", "launch", "monitor", "classify"]
RuntimeDiagnosisKind = Literal[
    "missing_dependency",
    "missing_fabric_api",
    "wrong_dependency_version",
    "duplicate_mod",
    "mod_id_conflict",
    "java_version_mismatch",
    "loader_mismatch",
    "unsupported_loader_runtime",
    "minecraft_version_mismatch",
    "mixin_failure",
    "side_mismatch",
    "corrupt_or_invalid_jar",
    "mod_conflict",
    "timeout",
    "crash_report",
    "unknown_launch_failure",
    "smoke_test_proof_missing",
    "weak_runtime_proof",
    "source_policy_blocked",
    # Compatibility aliases retained for reports/tests produced before V1 finalization.
    "missing_mod_dependency",
    "wrong_loader",
    "wrong_loader_version",
    "wrong_minecraft_version",
    "java_version_incompatible",
    "mixin_apply_failure",
    "fabric_api_missing",
    "config_parse_error",
    "access_widener_failure",
    "class_not_found",
    "no_such_method_error",
    "unsupported_mod_environment",
    "client_only_mod_on_server",
    "server_only_mod_on_client",
    "unknown_runtime_failure",
]
RuntimeDiagnosisConfidence = Literal["low", "medium", "high"]
RuntimeProofLevel = Literal[
    "none",
    "client_initialized",
    "main_menu_likely",
    "world_joined",
    "stable_30",
    "stable_60",
    "stable_120",
]


class RuntimeLaunchRequest(AgentSafeModel):
    instance_name: str
    minecraft_version: str
    loader: str
    loader_version: str | None = None
    mod_files: list[str]
    config_dir: str | None = None
    output_root: str | None = None
    memory_mb: int = 4096
    timeout_seconds: int = 180
    java_path: str | None = None
    offline_username: str = "MythWeaver"
    allow_network_downloads: bool = True
    stop_after_success: bool = True
    success_grace_seconds: int = 20
    inject_smoke_test: bool = True
    smoke_test_helper_path: str | None = None
    require_smoke_test_proof: bool = True
    minimum_stability_seconds: int = 60


class RuntimeProof(AgentSafeModel):
    proof_level: RuntimeProofLevel = "none"
    runtime_proof_observed: bool = False
    smoke_test_mod_used: bool = False
    smoke_test_markers_seen: list[str] = Field(default_factory=list)
    required_markers_met: bool = False
    stability_seconds_proven: int = 0
    evidence_path: str | None = None
    final_export_excluded_smoketest_mod: bool = True


class RuntimeIssue(AgentSafeModel):
    kind: str
    severity: RuntimeIssueSeverity
    confidence: float = Field(ge=0.0, le=1.0)
    message: str
    evidence: list[str]
    affected_mods: list[str] = Field(default_factory=list)
    missing_mods: list[str] = Field(default_factory=list)
    suspected_mods: list[str] = Field(default_factory=list)


class RuntimeAction(AgentSafeModel):
    action: RuntimeActionKind
    safety: RuntimeActionSafety
    reason: str
    query: str | None = None
    source_preference: list[str] = Field(default_factory=list)
    minecraft_version: str | None = None
    loader: str | None = None
    loader_version: str | None = None
    required: bool = True


class RuntimeDiagnosis(AgentSafeModel):
    kind: RuntimeDiagnosisKind
    confidence: RuntimeDiagnosisConfidence
    summary: str
    evidence: list[str] = Field(default_factory=list)
    blocking: bool = True
    affected_mod_ids: list[str] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    suggested_repair_action_kinds: list[RuntimeActionKind] = Field(default_factory=list)


class RuntimeLaunchReport(AgentSafeModel):
    status: RuntimeLaunchStatus
    stage: RuntimeLaunchStage
    instance_path: str | None
    minecraft_version: str
    loader: str
    loader_version: str | None
    java_path: str | None
    command_preview: list[str]
    exit_code: int | None
    success_signal: str | None
    issues: list[RuntimeIssue]
    recommended_next_actions: list[RuntimeAction]
    logs_scanned: list[str]
    warnings: list[str]
    proof: RuntimeProof | None = None
    diagnoses: list[RuntimeDiagnosis] = Field(default_factory=list)
