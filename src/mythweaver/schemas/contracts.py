from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mythweaver.catalog.content_kinds import ContentKind, ContentPlacement

SupportedLoader = Literal[
    "fabric",
    "forge",
    "neoforge",
    "quilt",
    "vanilla",
    "liteloader",
    "rift",
    "babric",
    "legacy_fabric",
    "unknown",
]
RequestedLoader = Literal[
    "fabric",
    "forge",
    "neoforge",
    "quilt",
    "vanilla",
    "liteloader",
    "rift",
    "babric",
    "legacy_fabric",
    "unknown",
    "auto",
    "any",
]
Loader = RequestedLoader
SideSupport = Literal["required", "optional", "unsupported", "unknown"]
DependencyType = Literal["required", "optional", "incompatible", "embedded"]
VersionType = Literal["release", "beta", "alpha"]
FoundationPolicyValue = Literal["enabled", "disabled", "auto"]
SelectedModRole = Literal["theme", "foundation", "utility", "shader_support", "dependency", "optional"]
RepairActionType = Literal[
    "remove_mod",
    "replace_mod",
    "disable_optional_mod",
    "change_mod_version",
    "add_missing_dependency",
    "remove_duplicate_system",
    "reduce_mod_count",
    "switch_shader_support_off",
    "mark_manual_review_required",
]


def _lower_list(values: list[str]) -> list[str]:
    return [value.strip().lower() for value in values if value and value.strip()]


def _is_hex(value: str, length: int) -> bool:
    if len(value) != length:
        return False
    return all(character in "0123456789abcdefABCDEF" for character in value)


class AgentSafeModel(BaseModel):
    """Base model configured for deterministic JSON contracts."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FoundationPolicy(AgentSafeModel):
    performance: FoundationPolicyValue = "auto"
    shaders: FoundationPolicyValue = "auto"
    utilities: FoundationPolicyValue = "auto"


class RequirementProfile(AgentSafeModel):
    """Structured intent supplied by an external coding agent or optional AI adapter."""

    name: str
    summary: str | None = None
    prompt: str | None = None
    themes: list[str] = Field(default_factory=list)
    terrain: list[str] = Field(default_factory=list)
    gameplay: list[str] = Field(default_factory=list)
    mood: list[str] = Field(default_factory=list)
    desired_systems: list[str] = Field(default_factory=list)
    search_keywords: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    preferred_capabilities: list[str] = Field(default_factory=list)
    forbidden_capabilities: list[str] = Field(default_factory=list)
    explicit_exclusions: list[str] = Field(default_factory=list)
    theme_anchors: list[str] = Field(default_factory=list)
    mood_anchors: list[str] = Field(default_factory=list)
    worldgen_anchors: list[str] = Field(default_factory=list)
    gameplay_anchors: list[str] = Field(default_factory=list)
    foundation_policy: FoundationPolicy = Field(default_factory=FoundationPolicy)
    max_selected_before_dependencies: int | None = Field(default=None, ge=1, le=250)
    combat_style: str | None = None
    pacing: str | None = None
    performance_target: Literal["low-end", "balanced", "high-end"] = "balanced"
    multiplayer: Literal["singleplayer", "multiplayer", "both"] = "singleplayer"
    loader: Loader = "fabric"
    minecraft_version: str = "auto"
    max_mods: int = Field(default=60, ge=1, le=250)

    @field_validator(
        "themes",
        "terrain",
        "gameplay",
        "mood",
        "desired_systems",
        "search_keywords",
        "negative_keywords",
        "required_capabilities",
        "preferred_capabilities",
        "forbidden_capabilities",
        "explicit_exclusions",
        "theme_anchors",
        "mood_anchors",
        "worldgen_anchors",
        "gameplay_anchors",
    )
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        return _lower_list(values)

    @field_validator("loader", "minecraft_version")
    @classmethod
    def normalize_string(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_profile_consistency(self) -> "RequirementProfile":
        if "shader_support" in self.required_capabilities and self.foundation_policy.shaders == "disabled":
            raise ValueError("shader_support requires foundation_policy.shaders to be enabled or auto")
        if (
            "performance_foundation" in self.required_capabilities
            and self.foundation_policy.performance == "disabled"
        ):
            raise ValueError("performance_foundation requires foundation_policy.performance to be enabled or auto")
        return self


class SearchPlan(AgentSafeModel):
    """Deterministic Modrinth search parameters."""

    query: str
    minecraft_version: str = "auto"
    loader: Loader = "fabric"
    project_type: Literal["mod", "modpack", "resourcepack", "shader", "datapack"] = "mod"
    categories: list[str] = Field(default_factory=list)
    client_side: SideSupport | None = None
    server_side: SideSupport | None = None
    index: Literal["relevance", "downloads", "follows", "newest", "updated"] = "relevance"
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    source_field: str | None = None
    weight: float = Field(default=1.0, ge=0.0)
    origin: Literal["explicit_profile", "archetype", "foundation", "fallback_extraction"] = "fallback_extraction"

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        return value

    @field_validator("categories")
    @classmethod
    def normalize_categories(cls, values: list[str]) -> list[str]:
        return _lower_list(values)

    @field_validator("loader", "minecraft_version")
    @classmethod
    def normalize_string(cls, value: str) -> str:
        return value.strip().lower()


class SelectedModEntry(AgentSafeModel):
    slug: str | None = None
    modrinth_id: str | None = None
    role: SelectedModRole = "theme"
    reason_selected: str | None = None
    required: bool = True
    alternatives: list[str] = Field(default_factory=list)
    source: Literal["modrinth", "curseforge", "github", "planetminecraft", "local", "direct_url", "auto"] = "auto"
    source_ref: str | None = None
    source_project_id: str | None = None
    source_file_id: str | None = None
    source_slug: str | None = None
    source_url: str | None = None
    preferred_source: Literal["modrinth", "curseforge", "github", "planetminecraft", "local", "direct_url", "auto"] | None = None
    allowed_sources: list[Literal["modrinth", "curseforge", "github", "planetminecraft", "local", "direct_url"]] = Field(default_factory=list)
    kind: ContentKind | None = None
    placement: ContentPlacement | None = None
    enabled_by_default: bool | None = None

    @field_validator("slug", "modrinth_id", "source_project_id", "source_file_id", "source_slug", "source_url", "source_ref")
    @classmethod
    def normalize_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        return stripped or None

    @field_validator("alternatives")
    @classmethod
    def normalize_alternatives(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]

    @model_validator(mode="after")
    def require_identifier(self) -> "SelectedModEntry":
        if not any(
            [
                self.slug,
                self.modrinth_id,
                self.source_ref,
                self.source_project_id,
                self.source_slug,
                self.source_url,
            ]
        ):
            raise ValueError("selected mod entry requires slug, modrinth_id, or source-specific ref")
        return self

    @model_validator(mode="after")
    def datapack_placement_entry(self) -> "SelectedModEntry":
        if self.kind == "datapack" and self.placement not in (None, "manual_world_creation"):
            raise ValueError("datapack selected rows must use placement manual_world_creation in MythWeaver v1")
        return self

    def identifier(self) -> str:
        return self.source_ref or self.source_project_id or self.source_slug or self.source_url or self.modrinth_id or self.slug or ""


class PackContentEntry(AgentSafeModel):
    """Structured non-mod (or mod) row for `SelectedModList.content`; sources are official APIs only."""

    slug: str
    source: Literal["modrinth", "curseforge"]
    kind: ContentKind
    required: bool = True
    placement: ContentPlacement | None = None
    enabled_by_default: bool | None = None
    notes: list[str] = Field(default_factory=list)
    reason: str | None = None
    conflicts: list[str] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def strip_slug(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("slug must not be empty")
        return value


    @model_validator(mode="after")
    def datapack_placement_only(self) -> "PackContentEntry":
        if self.kind == "datapack" and self.placement not in (None, "manual_world_creation"):
            raise ValueError("datapack content rows must use placement manual_world_creation in MythWeaver v1")
        return self


class SelectedModList(AgentSafeModel):
    name: str
    summary: str | None = None
    minecraft_version: str
    loader: Loader = "fabric"
    mods: list[SelectedModEntry] = Field(default_factory=list)
    content: list[PackContentEntry] = Field(default_factory=list)
    shader_recommendations: list[str] = Field(default_factory=list)
    notes: str | None = None
    repair_changelog: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("loader", "minecraft_version")
    @classmethod
    def normalize_string(cls, value: str) -> str:
        return value.strip().lower()


class GameplayLoop(AgentSafeModel):
    name: str
    description: str
    repeated_player_actions: list[str] = Field(default_factory=list)
    reward_types: list[str] = Field(default_factory=list)
    friction_points: list[str] = Field(default_factory=list)


class ProgressionPhase(AgentSafeModel):
    name: str
    purpose: str
    expected_player_actions: list[str] = Field(default_factory=list)
    required_systems: list[str] = Field(default_factory=list)
    reward_types: list[str] = Field(default_factory=list)
    pacing_notes: str | None = None


class PackDesignPillar(AgentSafeModel):
    name: str
    priority: Literal["core", "supporting", "optional"] = "supporting"
    description: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    anti_goals: list[str] = Field(default_factory=list)


class PackDesign(AgentSafeModel):
    name: str
    summary: str
    minecraft_version: str = "1.20.1"
    loader: Loader = "fabric"
    archetype: Literal[
        "vanilla_plus",
        "rpg_adventure",
        "dark_fantasy",
        "expert_tech",
        "tech_automation",
        "magic_progression",
        "kitchen_sink",
        "skyblock",
        "stoneblock",
        "horror_survival",
        "cozy_farming",
        "exploration_survival",
        "hardcore_survival",
        "building_creative",
        "multiplayer_smp",
        "questing_adventure",
        "custom",
    ] = "custom"
    audience: str | None = None
    intended_session_style: Literal[
        "short_sessions",
        "long_sessions",
        "server_multiplayer",
        "solo_world",
        "challenge_run",
        "creative_building",
        "mixed",
    ] = "mixed"
    difficulty_target: Literal["relaxed", "normal", "challenging", "hardcore", "expert"] = "normal"
    pillars: list[PackDesignPillar] = Field(default_factory=list)
    core_loops: list[GameplayLoop] = Field(default_factory=list)
    progression_phases: list[ProgressionPhase] = Field(default_factory=list)
    required_systems: list[str] = Field(default_factory=list)
    forbidden_systems: list[str] = Field(default_factory=list)
    soft_allowed_systems: list[str] = Field(default_factory=list)
    must_have_experience_beats: list[str] = Field(default_factory=list)
    optional_experience_beats: list[str] = Field(default_factory=list)
    mod_selection_rules: list[str] = Field(default_factory=list)
    config_or_datapack_needs: list[str] = Field(default_factory=list)
    quality_bar: list[str] = Field(default_factory=list)

    @field_validator(
        "required_systems",
        "forbidden_systems",
        "soft_allowed_systems",
    )
    @classmethod
    def normalize_design_system_lists(cls, values: list[str]) -> list[str]:
        return _lower_list(values)

    @field_validator(
        "must_have_experience_beats",
        "optional_experience_beats",
        "mod_selection_rules",
        "config_or_datapack_needs",
        "quality_bar",
    )
    @classmethod
    def strip_design_text_lists(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]

    @field_validator("loader", "minecraft_version")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return value.strip().lower()


class PackDesignReviewIssue(AgentSafeModel):
    severity: Literal["info", "warning", "high", "critical"]
    category: str
    title: str
    detail: str | None = None
    suggested_action: str | None = None


class PackDesignReviewReport(AgentSafeModel):
    run_id: str
    status: Literal["passed", "warnings", "failed"]
    score: int = Field(default=0, ge=0, le=100)
    verdict: str
    readiness: Literal["ready_for_mod_selection", "revise_design_first", "not_enough_direction"]
    design: PackDesign
    issues: list[PackDesignReviewIssue] = Field(default_factory=list)
    missing_design_elements: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    cloud_ai_prompt_path: str | None = None
    output_dir: str | None = None


class ModBlueprintSlot(AgentSafeModel):
    slot_id: str
    system_tag: str
    priority: Literal["required", "recommended", "optional", "forbidden"]
    purpose: str
    min_count: int = Field(default=0, ge=0)
    max_count: int = Field(default=1, ge=0)
    search_terms: list[str] = Field(default_factory=list)
    selection_rules: list[str] = Field(default_factory=list)
    avoid_rules: list[str] = Field(default_factory=list)
    supports_phases: list[str] = Field(default_factory=list)
    supports_loops: list[str] = Field(default_factory=list)

    @field_validator("system_tag", "priority")
    @classmethod
    def normalize_blueprint_strings(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator(
        "search_terms",
        "selection_rules",
        "avoid_rules",
        "supports_phases",
        "supports_loops",
    )
    @classmethod
    def strip_blueprint_lists(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]

    @model_validator(mode="after")
    def validate_count_range(self) -> "ModBlueprintSlot":
        if self.max_count < self.min_count:
            raise ValueError("max_count must be greater than or equal to min_count")
        return self


class PackBlueprint(AgentSafeModel):
    name: str
    minecraft_version: str
    loader: Loader = "fabric"
    archetype: str
    summary: str
    target_mod_count_min: int = Field(ge=0)
    target_mod_count_max: int = Field(ge=0)
    required_slots: list[ModBlueprintSlot] = Field(default_factory=list)
    recommended_slots: list[ModBlueprintSlot] = Field(default_factory=list)
    optional_slots: list[ModBlueprintSlot] = Field(default_factory=list)
    forbidden_slots: list[ModBlueprintSlot] = Field(default_factory=list)
    compatibility_cautions: list[str] = Field(default_factory=list)
    config_or_datapack_expectations: list[str] = Field(default_factory=list)
    quest_expectations: list[str] = Field(default_factory=list)
    quality_bar: list[str] = Field(default_factory=list)
    output_dir: str | None = None
    cloud_ai_prompt_path: str | None = None

    @field_validator("loader", "minecraft_version", "archetype")
    @classmethod
    def normalize_blueprint_target(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator(
        "compatibility_cautions",
        "config_or_datapack_expectations",
        "quest_expectations",
        "quality_bar",
    )
    @classmethod
    def strip_blueprint_text_lists(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]

    @model_validator(mode="after")
    def validate_target_mod_count_range(self) -> "PackBlueprint":
        if self.target_mod_count_max < self.target_mod_count_min:
            raise ValueError("target_mod_count_max must be greater than or equal to target_mod_count_min")
        return self


class DependencyRecord(AgentSafeModel):
    version_id: str | None = None
    project_id: str | None = None
    file_name: str | None = None
    dependency_type: DependencyType


class ModFile(AgentSafeModel):
    filename: str
    url: str
    hashes: dict[str, str]
    size: int = Field(alias="fileSize", ge=0)
    primary: bool = False
    file_type: str | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_assignment=True)

    @field_validator("hashes")
    @classmethod
    def require_download_hashes(cls, hashes: dict[str, str]) -> dict[str, str]:
        """Modrinth supplies sha1+sha512; CurseForge often supplies sha1 only — at least one strong hash is required."""
        sha1 = hashes.get("sha1")
        sha512 = hashes.get("sha512")
        if sha1 and not _is_hex(sha1, 40):
            raise ValueError("sha1 must be 40 hexadecimal characters")
        if sha512 and not _is_hex(sha512, 128):
            raise ValueError("sha512 must be 128 hexadecimal characters")
        if not sha1 and not sha512:
            raise ValueError("hashes must include sha1 and/or sha512")
        return hashes

    @field_validator("url")
    @classmethod
    def require_safe_download_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https":
            raise ValueError("download URL must use HTTPS")
        if " " in value:
            raise ValueError("download URL must not contain unencoded spaces")
        if not parsed.netloc:
            raise ValueError("download URL must include a host")
        return value


class ModVersion(AgentSafeModel):
    id: str
    project_id: str
    version_number: str
    game_versions: list[str]
    loaders: list[str]
    version_type: VersionType
    status: Literal["listed", "archived", "draft", "unlisted", "scheduled", "unknown"]
    dependencies: list[DependencyRecord] = Field(default_factory=list)
    files: list[ModFile] = Field(default_factory=list)
    date_published: str | None = None
    downloads: int = 0

    @field_validator("loaders", "game_versions")
    @classmethod
    def normalize_values(cls, values: list[str]) -> list[str]:
        return _lower_list(values)

    def primary_file(self) -> ModFile:
        if not self.files:
            raise ValueError(f"version {self.id} has no files")
        for file in self.files:
            if file.primary:
                return file
        return self.files[0]


class ModScore(AgentSafeModel):
    total: float = 0.0
    relevance: float = 0.0
    quality: float = 0.0
    compatibility: float = 0.0
    performance: float = 0.0
    dependency_penalty: float = 0.0
    overlap_penalty: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    hard_reject_reason: str | None = None


class CandidateMod(AgentSafeModel):
    project_id: str
    slug: str
    title: str
    description: str = ""
    categories: list[str] = Field(default_factory=list)
    client_side: SideSupport = "unknown"
    server_side: SideSupport = "unknown"
    downloads: int = 0
    follows: int = 0
    updated: str | None = None
    loaders: list[str] = Field(default_factory=list)
    game_versions: list[str] = Field(default_factory=list)
    selected_version: ModVersion
    dependency_count: int = 0
    body: str | None = None
    score: ModScore = Field(default_factory=ModScore)
    why_selected: list[str] = Field(default_factory=list)
    matched_profile_terms: list[str] = Field(default_factory=list)
    matched_capabilities: list[str] = Field(default_factory=list)
    penalties_applied: list[str] = Field(default_factory=list)
    rejection_risk: str | None = None
    selection_type: Literal[
        "selected_theme_mod",
        "selected_foundation_mod",
        "dependency_added",
        "optional_recommendation",
    ] = "selected_theme_mod"
    content_kind: ContentKind = "mod"
    content_placement: ContentPlacement | None = None
    platform_project_type: str | None = None
    enabled_by_default: bool | None = None

    @field_validator("categories", "loaders", "game_versions")
    @classmethod
    def normalize_values(cls, values: list[str]) -> list[str]:
        return _lower_list(values)

    def primary_file(self) -> ModFile:
        return self.selected_version.primary_file()

    def searchable_text(self) -> str:
        pieces = [self.title, self.description, self.body or "", " ".join(self.categories)]
        return " ".join(pieces).lower()


class RejectedMod(AgentSafeModel):
    project_id: str
    title: str | None = None
    reason: str
    detail: str | None = None


class RemovedSelectedMod(AgentSafeModel):
    slug_or_id: str
    title: str | None = None
    reason: str
    original_role: str | None = None
    category_impact: list[str] = Field(default_factory=list)
    replacement_search_terms: list[str] = Field(default_factory=list)


class DependencyEdge(AgentSafeModel):
    source_project_id: str
    target_project_id: str
    dependency_type: DependencyType


class SourceDependencyRecord(AgentSafeModel):
    source: Literal["modrinth", "curseforge", "github", "planetminecraft", "local", "direct_url", "unknown"] = "unknown"
    project_id: str | None = None
    version_id: str | None = None
    file_name: str | None = None
    dependency_type: DependencyType = "required"
    required_version: str | None = None
    required_by: str | None = None


class BuildArtifact(AgentSafeModel):
    kind: str
    path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolvedPack(AgentSafeModel):
    name: str
    minecraft_version: str
    loader: Loader = "fabric"
    loader_version: str | None = None
    selected_mods: list[CandidateMod] = Field(default_factory=list)
    rejected_mods: list[RejectedMod] = Field(default_factory=list)
    dependency_edges: list[DependencyEdge] = Field(default_factory=list)
    conflicts: list[RejectedMod] = Field(default_factory=list)
    config_actions: list[str] = Field(default_factory=list)
    artifacts: list[BuildArtifact] = Field(default_factory=list)


class FailureAnalysis(AgentSafeModel):
    classification: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    repair_candidates: list[str] = Field(default_factory=list)
    likely_causes: list[str] = Field(default_factory=list)


class ValidationReport(AgentSafeModel):
    status: Literal["passed", "failed", "skipped", "timeout"]
    validation_status: str | None = None
    prism_executable_path: str | None = None
    prism_instances_path: str | None = None
    pack_path: str | None = None
    instance_path: str | None = None
    log_path: str | None = None
    latest_log_path: str | None = None
    analysis: FailureAnalysis | None = None
    details: str | None = None
    launched: bool = False
    logs_collected: list[str] = Field(default_factory=list)
    crash_report_path: str | None = None
    crash_report_paths: list[str] = Field(default_factory=list)
    suspected_failure_type: str | None = None
    likely_causes: list[str] = Field(default_factory=list)
    suspected_mods: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    suggested_actions: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    raw_summary: str | None = None


class RepairOption(AgentSafeModel):
    id: str
    action_type: RepairActionType
    target_mod: str | None = None
    target_mod_id: str | None = None
    target_slug: str | None = None
    replacement_query: str | None = None
    replacement_candidates: list[dict[str, Any]] = Field(default_factory=list)
    reason: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high"] = "medium"
    expected_effect: str | None = None
    tradeoffs: list[str] = Field(default_factory=list)
    requires_agent_review: bool = True


class RepairReport(AgentSafeModel):
    pack_name: str
    source_report_path: str
    validation_status: str = "unknown"
    failed_stage: str | None = None
    crash_classification: str = "unknown"
    suspected_mods: list[str] = Field(default_factory=list)
    repair_options: list[RepairOption] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    next_actions: list[str] = Field(default_factory=list)
    memory_advisories: list[dict[str, Any]] = Field(default_factory=list)


class ReviewIssue(AgentSafeModel):
    severity: Literal["info", "warning", "high", "critical"]
    category: str
    title: str
    detail: str | None = None
    affected_mods: list[str] = Field(default_factory=list)
    suggested_action: str | None = None
    replacement_search_terms: list[str] = Field(default_factory=list)


class PillarCoverage(AgentSafeModel):
    pillar: str
    status: Literal["missing", "thin", "covered", "overloaded"]
    matching_mods: list[str] = Field(default_factory=list)
    detail: str | None = None
    suggested_search_terms: list[str] = Field(default_factory=list)


class DependencyImpactReport(AgentSafeModel):
    user_selected_count: int = 0
    dependency_added_count: int = 0
    dependency_added_mods: list[str] = Field(default_factory=list)
    missing_dependencies: list[RejectedMod] = Field(default_factory=list)
    dependency_edges: list[DependencyEdge] = Field(default_factory=list)


class SelectedModReviewReport(AgentSafeModel):
    run_id: str
    status: Literal["passed", "warnings", "failed"]
    name: str
    summary: str | None = None
    minecraft_version: str
    loader: Loader = "fabric"
    score: int = Field(default=0, ge=0, le=100)
    verdict: str
    build_recommendation: Literal["build", "revise_first", "do_not_build"]
    pillars: list[PillarCoverage] = Field(default_factory=list)
    issues: list[ReviewIssue] = Field(default_factory=list)
    duplicate_systems: list[ReviewIssue] = Field(default_factory=list)
    risky_combinations: list[ReviewIssue] = Field(default_factory=list)
    stale_or_low_signal_mods: list[ReviewIssue] = Field(default_factory=list)
    novelty_or_off_theme_mods: list[ReviewIssue] = Field(default_factory=list)
    dependency_impact: DependencyImpactReport = Field(default_factory=DependencyImpactReport)
    recommended_replacement_searches: list[str] = Field(default_factory=list)
    cloud_ai_prompt_path: str | None = None
    output_dir: str | None = None
    next_actions: list[str] = Field(default_factory=list)
    pack_design_path: str | None = None
    archetype: str | None = None
    design_alignment_score: int = Field(default=0, ge=0, le=100)
    missing_required_systems: list[str] = Field(default_factory=list)
    weak_required_systems: list[str] = Field(default_factory=list)
    anti_goal_violations: list[ReviewIssue] = Field(default_factory=list)
    progression_gaps: list[ReviewIssue] = Field(default_factory=list)
    cohesion_issues: list[ReviewIssue] = Field(default_factory=list)
    pacing_issues: list[ReviewIssue] = Field(default_factory=list)
    config_or_datapack_warnings: list[ReviewIssue] = Field(default_factory=list)
    system_coverage: dict[str, list[str]] = Field(default_factory=dict)
    removed_mods: list[RemovedSelectedMod] = Field(default_factory=list)


class AgentCheckFinding(AgentSafeModel):
    severity: Literal["info", "warning", "high", "critical"]
    kind: Literal[
        "technical_blocker",
        "compatibility_risk",
        "dependency_issue",
        "removed_mod",
        "possible_duplicate",
        "theme_signal",
        "stale_or_low_signal",
        "performance_signal",
        "ai_judgment_needed",
    ]
    title: str
    detail: str | None = None
    affected_mods: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    ai_instruction: str | None = None
    suggested_search_terms: list[str] = Field(default_factory=list)


class AgentCheckReport(AgentSafeModel):
    name: str
    minecraft_version: str
    loader: Loader = "fabric"
    status: Literal["ok", "needs_ai_revision", "blocked"]
    build_permission: Literal["allowed", "allowed_with_warnings", "blocked"]
    summary: str
    hard_blockers: list[AgentCheckFinding] = Field(default_factory=list)
    warnings: list[AgentCheckFinding] = Field(default_factory=list)
    ai_judgment_needed: list[AgentCheckFinding] = Field(default_factory=list)
    dependency_summary: DependencyImpactReport | None = None
    removed_mods: list[RemovedSelectedMod] = Field(default_factory=list)
    suggested_replacement_searches: list[str] = Field(default_factory=list)
    next_recommended_steps: list[str] = Field(default_factory=list)
    cloud_ai_prompt_path: str | None = None
    output_dir: str | None = None


class AgentWorkflowStep(AgentSafeModel):
    step_id: str
    title: str
    purpose: str
    command: str | None = None
    expected_outputs: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    failure_handling: list[str] = Field(default_factory=list)


class AgentWorkflowPromptReport(AgentSafeModel):
    name: str
    concept_path: str
    output_dir: str
    prompt_path: str
    workflow_manifest_path: str
    recommended_steps: list[AgentWorkflowStep] = Field(default_factory=list)
    summary: str


class CrashFinding(AgentSafeModel):
    severity: Literal["info", "warning", "high", "critical"]
    kind: Literal[
        "missing_class",
        "missing_mod",
        "dependency_version_mismatch",
        "kotlin_reflection_error",
        "mixin_failure",
        "entrypoint_failure",
        "world_join_crash",
        "loader_error",
        "mod_conflict",
        "external_dependency_risk",
        "final_artifact_invalid",
        "unknown_runtime_error",
    ]
    title: str
    detail: str | None = None
    crashing_mod_id: str | None = None
    suspected_mods: list[str] = Field(default_factory=list)
    missing_class: str | None = None
    missing_mod_id: str | None = None
    suggested_actions: list[str] = Field(default_factory=list)
    ai_instruction: str | None = None


class CrashAnalysisReport(AgentSafeModel):
    status: Literal["identified", "partial", "unknown"]
    crash_report_path: str
    selected_mods_path: str | None = None
    summary: str
    crashing_mod_id: str | None = None
    findings: list[CrashFinding] = Field(default_factory=list)
    repair_recommendation: Literal[
        "replace_mod",
        "pin_dependency_version",
        "add_missing_dependency",
        "remove_mod",
        "clear_config",
        "manual_review_required",
        "unknown",
    ] = "unknown"
    output_dir: str | None = None
    cloud_ai_prompt_path: str | None = None


class LaunchValidationReport(AgentSafeModel):
    status: Literal["passed", "failed", "skipped", "manual_required"]
    stage: Literal[
        "not_started",
        "launcher_setup",
        "game_start",
        "main_menu",
        "world_create",
        "world_join",
        "runtime_wait",
        "complete",
    ] = "not_started"
    summary: str
    crash_report_path: str | None = None
    crash_analysis: CrashAnalysisReport | None = None
    log_path: str | None = None
    seconds_observed: int = 0
    output_dir: str | None = None
    evidence_path: str | None = None
    detected_markers: list[str] = Field(default_factory=list)
    process_exit_code: int | None = None
    freeze_detected: bool = False
    smoke_test_mod_injected: bool = False
    smoke_test_markers_seen: list[str] = Field(default_factory=list)
    marker_timestamps: dict[str, str] = Field(default_factory=dict)
    required_markers_met: bool = False
    stability_seconds_proven: int = 0
    runtime_proof_observed: bool = False
    final_export_excluded_smoketest_mod: bool = True
    validation_world_created: bool = False
    validation_world_cleaned: bool = False
    validation_world_path: str | None = None


class SmokeTestInjectionReport(AgentSafeModel):
    status: Literal["injected", "already_present", "missing_helper", "failed", "skipped"]
    helper_mod_path: str | None = None
    instance_mods_path: str | None = None
    injected_file_path: str | None = None
    removed_after_validation: bool = False
    final_export_excluded: bool = True
    notes: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ValidationWorldReport(AgentSafeModel):
    status: Literal["created", "already_present", "removed", "failed", "skipped"]
    world_name: str = "MythWeaverRuntimeSmokeTest"
    saves_path: str | None = None
    world_path: str | None = None
    removed_after_validation: bool = False
    final_export_excluded: bool = True
    notes: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class StabilizationAttempt(AgentSafeModel):
    attempt_number: int
    selected_mods_path: str
    verify_status: Literal["passed", "failed", "skipped"]
    dry_run_status: Literal["passed", "failed", "skipped"]
    launch_status: Literal["passed", "failed", "skipped", "manual_required"]
    crash_summary: str | None = None
    changes_made: list[str] = Field(default_factory=list)
    removed_mods: list[RemovedSelectedMod] = Field(default_factory=list)


class StabilizationReport(AgentSafeModel):
    name: str
    status: Literal["stable", "needs_manual_review", "failed"]
    summary: str
    attempts: list[StabilizationAttempt] = Field(default_factory=list)
    final_selected_mods_path: str | None = None
    final_output_dir: str | None = None
    unresolved_findings: list[CrashFinding] = Field(default_factory=list)
    output_dir: str | None = None


class LauncherDetectionReport(AgentSafeModel):
    status: Literal["found", "not_found", "ambiguous", "manual_required"]
    launcher_name: str
    install_paths: list[str] = Field(default_factory=list)
    data_paths: list[str] = Field(default_factory=list)
    executable_paths: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class LauncherInstanceReport(AgentSafeModel):
    status: Literal["created", "imported", "failed", "manual_required"]
    launcher_name: str
    instance_name: str
    instance_path: str | None = None
    generated_instance_path: str | None = None
    prism_registered_instance_path: str | None = None
    prism_instance_id: str | None = None
    registered_with_prism: bool = False
    pack_artifact_path: str | None = None
    minecraft_version: str
    loader: str
    loader_version: str | None = None
    memory_mb: int
    notes: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class LauncherValidationIssue(AgentSafeModel):
    severity: Literal["info", "warning", "high", "critical"]
    kind: Literal[
        "missing_loader",
        "wrong_loader",
        "wrong_minecraft_version",
        "wrong_loader_version",
        "memory_not_set",
        "memory_too_low",
        "missing_mods_folder",
        "missing_instance_metadata",
        "vanilla_instance",
        "unknown",
    ]
    title: str
    detail: str | None = None
    suggested_fix: str | None = None


class LauncherValidationReport(AgentSafeModel):
    status: Literal["passed", "failed", "manual_required"]
    launcher_name: str
    instance_path: str | None = None
    minecraft_version: str | None = None
    loader: str | None = None
    loader_version: str | None = None
    memory_mb: int | None = None
    issues: list[LauncherValidationIssue] = Field(default_factory=list)
    summary: str


class RuntimeSmokeTestReport(AgentSafeModel):
    status: Literal["passed", "failed", "skipped", "manual_required"]
    stage: Literal[
        "not_started",
        "launcher_start",
        "main_menu",
        "world_create",
        "world_join",
        "runtime_wait",
        "complete",
    ] = "not_started"
    seconds_observed: int = 0
    latest_log_path: str | None = None
    crash_report_path: str | None = None
    crash_analysis: CrashAnalysisReport | None = None
    summary: str
    notes: list[str] = Field(default_factory=list)
    evidence_path: str | None = None
    detected_markers: list[str] = Field(default_factory=list)
    process_exit_code: int | None = None
    freeze_detected: bool = False
    smoke_test_mod_injected: bool = False
    smoke_test_markers_seen: list[str] = Field(default_factory=list)
    marker_timestamps: dict[str, str] = Field(default_factory=dict)
    required_markers_met: bool = False
    stability_seconds_proven: int = 0
    runtime_proof_observed: bool = False
    final_export_excluded_smoketest_mod: bool = True
    validation_world_created: bool = False
    validation_world_cleaned: bool = False
    validation_world_path: str | None = None


class AutonomousBuildAttempt(AgentSafeModel):
    attempt_number: int
    selected_mods_path: str
    build_report_path: str | None = None
    launcher_instance_report: LauncherInstanceReport | None = None
    launcher_validation_report: LauncherValidationReport | None = None
    runtime_smoke_test_report: RuntimeSmokeTestReport | None = None
    changes_made: list[str] = Field(default_factory=list)
    removed_mods: list[RemovedSelectedMod] = Field(default_factory=list)


class AutonomousBuildReport(AgentSafeModel):
    name: str
    status: Literal["stable", "needs_manual_review", "failed"]
    summary: str
    attempts: list[AutonomousBuildAttempt] = Field(default_factory=list)
    final_selected_mods_path: str | None = None
    final_instance_path: str | None = None
    final_pack_artifact_path: str | None = None
    output_dir: str | None = None
    final_status_reason: str | None = None
    runtime_proof_required: bool = True
    runtime_proof_observed: bool = False
    smoke_test_mod_used: bool = False
    stability_seconds_proven: int = 0
    manual_required_reason: str | None = None
    user_next_steps: list[str] = Field(default_factory=list)


class PipelineStageResult(AgentSafeModel):
    name: str
    status: Literal["pending", "completed", "failed", "skipped"]
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchStrategy(AgentSafeModel):
    profile: RequirementProfile
    search_plans: list[SearchPlan]


class CandidateSelection(AgentSafeModel):
    selected_project_ids: list[str]
    rejected_mods: list[RejectedMod] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    pillar_coverage: dict[str, dict[str, Any]] = Field(default_factory=dict)
    novelty_mods_selected: list[str] = Field(default_factory=list)
    performance_foundation_gaps: list[str] = Field(default_factory=list)
    overrepresented_concepts: list[str] = Field(default_factory=list)


class FoundationTarget(AgentSafeModel):
    capability: str
    queries: list[str] = Field(default_factory=list)
    loader: Loader = "fabric"
    required: bool = False
    budget_role: Literal["foundation", "visual", "utility"] = "foundation"


class ShaderRecommendation(AgentSafeModel):
    name: str = ""
    category: str = ""
    source: str = "recommendation"
    reason: str = ""
    installable: bool = False


class ShaderRecommendationSet(AgentSafeModel):
    primary: ShaderRecommendation = Field(default_factory=ShaderRecommendation)
    backups: list[ShaderRecommendation] = Field(default_factory=list)
    low_end_fallback: ShaderRecommendation | None = None
    installed: bool = False
    install_reason: str = "Shader packs are recommendations unless a verified allowed source permits bundling."


class SourceFileCandidate(AgentSafeModel):
    source: Literal[
        "modrinth",
        "curseforge",
        "github",
        "planetminecraft",
        "local",
        "direct_url",
        "unknown",
    ]
    project_id: str | None = None
    file_id: str | None = None
    slug: str | None = None
    name: str
    version_number: str | None = None
    minecraft_versions: list[str] = Field(default_factory=list)
    loaders: list[str] = Field(default_factory=list)
    file_name: str | None = None
    download_url: str | None = None
    page_url: str | None = None
    hashes: dict[str, str] = Field(default_factory=dict)
    file_size_bytes: int | None = None
    dependencies: list[str] = Field(default_factory=list)
    dependency_records: list[SourceDependencyRecord] = Field(default_factory=list)
    side: Literal["client", "server", "both", "unknown"] = "unknown"
    license: str | None = None
    distribution_allowed: Literal["yes", "no", "unknown"] = "unknown"
    metadata_confidence: Literal["low", "medium", "high"] = "low"
    acquisition_status: Literal[
        "verified_auto",
        "verified_manual_required",
        "metadata_incomplete",
        "download_blocked",
        "license_blocked",
        "unsafe_source",
        "unsupported",
    ] = "metadata_incomplete"
    warnings: list[str] = Field(default_factory=list)
    content_kind: ContentKind = "mod"
    content_placement: ContentPlacement | None = None
    enabled_by_default: bool | None = None


class SourceSearchResult(AgentSafeModel):
    query: str
    source: str
    candidates: list[SourceFileCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SourceResolveReport(AgentSafeModel):
    status: Literal["resolved", "partial", "failed"]
    minecraft_version: str
    loader: str
    selected_files: list[SourceFileCandidate] = Field(default_factory=list)
    manifest_files: list[SourceFileCandidate] = Field(default_factory=list)
    manual_required: list[SourceFileCandidate] = Field(default_factory=list)
    blocked: list[SourceFileCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_count: int = 0
    missing_count: int = 0
    unsupported_count: int = 0
    manual_required_count: int = 0
    export_supported: bool = False
    export_blockers: list[str] = Field(default_factory=list)
    unresolved_required_dependencies: list[RejectedMod] = Field(default_factory=list)
    manually_required_dependencies: list[SourceFileCandidate] = Field(default_factory=list)
    optional_dependencies: list[SourceDependencyRecord] = Field(default_factory=list)
    incompatible_dependencies: list[SourceDependencyRecord] = Field(default_factory=list)
    transitive_dependency_count: int = 0
    dependency_source_breakdown: dict[str, int] = Field(default_factory=dict)
    dependency_closure_passed: bool = False


class TargetCoverageRecord(AgentSafeModel):
    source: str
    selected_count: int = 0
    manual_required_count: int = 0
    blocked_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class TargetCandidate(AgentSafeModel):
    minecraft_version: str
    loader: str
    sources: list[str] = Field(default_factory=list)
    selected_count: int = 0
    required_count: int = 0
    missing_count: int = 0
    unsupported_count: int = 0
    manual_required_count: int = 0
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TargetMatrixReport(AgentSafeModel):
    requested_minecraft_version: str
    requested_loader: str
    considered_versions: list[str] = Field(default_factory=list)
    considered_loaders: list[str] = Field(default_factory=list)
    best: TargetCandidate | None = None
    candidates: list[TargetCandidate] = Field(default_factory=list)
    status: Literal["resolved", "partial", "failed"] = "failed"
    warnings: list[str] = Field(default_factory=list)


class PerformanceFoundationReport(AgentSafeModel):
    performance_enabled: bool = False
    shader_support_enabled: bool = False
    loader: Loader = "fabric"
    targets: list[FoundationTarget] = Field(default_factory=list)
    search_targets: list[str] = Field(default_factory=list)
    selected_mods: list[str] = Field(default_factory=list)
    rejected_mods: list[RejectedMod] = Field(default_factory=list)
    budget_note: str = "Foundation mods use a small reserved budget so theme mods remain the majority."
    opt_out_phrases: list[str] = Field(default_factory=list)
    shader_recommendations: ShaderRecommendationSet = Field(default_factory=ShaderRecommendationSet)


class ShaderSupportReport(AgentSafeModel):
    enabled: bool = False
    selected_project_ids: list[str] = Field(default_factory=list)
    installed_shader_packs: list[str] = Field(default_factory=list)
    installed: bool = False
    reason: str = ""


class ConfidenceScores(AgentSafeModel):
    theme_match: float = Field(default=0.0, ge=0.0, le=1.0)
    compatibility: float = Field(default=0.0, ge=0.0, le=1.0)
    dependency_resolution: float = Field(default=0.0, ge=0.0, le=1.0)
    pack_coherence: float = Field(default=0.0, ge=0.0, le=1.0)
    performance_foundation: float = Field(default=0.0, ge=0.0, le=1.0)
    visual_foundation: float = Field(default=0.0, ge=0.0, le=1.0)
    build_readiness: float = Field(default=0.0, ge=0.0, le=1.0)


class GenerationRequest(AgentSafeModel):
    prompt: str | None = None
    profile: RequirementProfile | None = None
    output_dir: str | None = None
    dry_run: bool = False
    limit: int = Field(default=20, ge=1, le=100)
    max_mods: int = Field(default=45, ge=1, le=100)
    loader_version: str | None = None
    strict_profile_mode: bool | None = None

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def require_prompt_or_profile(self) -> "GenerationRequest":
        if self.prompt is None and self.profile is None:
            raise ValueError("generation requires either prompt or profile")
        return self


class GenerationPlan(AgentSafeModel):
    profile: RequirementProfile
    strategy: SearchStrategy
    minecraft_version: str
    output_dir: str
    dry_run: bool


class GenerationReport(AgentSafeModel):
    run_id: str
    status: Literal["completed", "failed"]
    profile: RequirementProfile
    strict_profile_mode: bool = False
    minecraft_version: str | None = None
    failed_stage: str | None = None
    stages: list[PipelineStageResult] = Field(default_factory=list)
    search_plans: list[SearchPlan] = Field(default_factory=list)
    selected_mods: list[CandidateMod] = Field(default_factory=list)
    selected_theme_mods: list[CandidateMod] = Field(default_factory=list)
    selected_foundation_mods: list[CandidateMod] = Field(default_factory=list)
    dependency_added_mods: list[CandidateMod] = Field(default_factory=list)
    optional_recommendations: list[CandidateMod] = Field(default_factory=list)
    rejected_mods: list[RejectedMod] = Field(default_factory=list)
    dependency_edges: list[DependencyEdge] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    duplicate_system_warnings: list[str] = Field(default_factory=list)
    off_theme_selected_mods: list[str] = Field(default_factory=list)
    explicit_exclusion_violations: list[str] = Field(default_factory=list)
    forbidden_capability_violations: list[str] = Field(default_factory=list)
    low_evidence_selected_mods: list[str] = Field(default_factory=list)
    missing_required_capabilities: list[str] = Field(default_factory=list)
    duplicate_system_groups: list[str] = Field(default_factory=list)
    selected_mod_budget_breakdown: dict[str, int] = Field(default_factory=dict)
    suggested_search_refinements: list[str] = Field(default_factory=list)
    pillar_coverage: dict[str, dict[str, Any]] = Field(default_factory=dict)
    overrepresented_concepts: list[str] = Field(default_factory=list)
    novelty_mods_selected: list[str] = Field(default_factory=list)
    rejected_penalized_novelty_mods: list[str] = Field(default_factory=list)
    performance_foundation_gaps: list[str] = Field(default_factory=list)
    suggested_targeted_searches: list[str] = Field(default_factory=list)
    top_blockers: list[str] = Field(default_factory=list)
    performance_foundation: PerformanceFoundationReport = Field(default_factory=PerformanceFoundationReport)
    shader_support: ShaderSupportReport = Field(default_factory=ShaderSupportReport)
    shader_recommendations: ShaderRecommendationSet = Field(default_factory=ShaderRecommendationSet)
    confidence: ConfidenceScores = Field(default_factory=ConfidenceScores)
    artifacts: list[BuildArtifact] = Field(default_factory=list)
    validation: ValidationReport = Field(
        default_factory=lambda: ValidationReport(status="skipped", details="Validation not run.")
    )
    next_actions: list[str] = Field(default_factory=list)
    output_dir: str | None = None
    removed_mods: list[RemovedSelectedMod] = Field(default_factory=list)


class AgentPackReport(AgentSafeModel):
    run_id: str
    status: Literal["completed", "failed"]
    name: str
    summary: str | None = None
    minecraft_version: str
    loader: Loader = "fabric"
    failed_stage: str | None = None
    user_selected_mods: list[CandidateMod] = Field(default_factory=list)
    dependency_added_mods: list[CandidateMod] = Field(default_factory=list)
    selected_mods: list[CandidateMod] = Field(default_factory=list)
    rejected_mods: list[RejectedMod] = Field(default_factory=list)
    unresolved_mods: list[RejectedMod] = Field(default_factory=list)
    missing_dependencies: list[RejectedMod] = Field(default_factory=list)
    unresolved_required_dependencies: list[RejectedMod] = Field(default_factory=list)
    manually_required_dependencies: list[SourceFileCandidate] = Field(default_factory=list)
    transitive_dependency_count: int = 0
    dependency_source_breakdown: dict[str, int] = Field(default_factory=dict)
    dependency_closure_passed: bool = False
    incompatible_mods: list[RejectedMod] = Field(default_factory=list)
    compatibility_warnings: list[str] = Field(default_factory=list)
    duplicate_system_warnings: list[str] = Field(default_factory=list)
    recommended_replacements: list[dict[str, str]] = Field(default_factory=list)
    validation_status: str | None = None
    launch_validation: ValidationReport | None = None
    logs_collected: list[str] = Field(default_factory=list)
    crash_analysis: FailureAnalysis | None = None
    compatibility_memory_updates: list[str] = Field(default_factory=list)
    known_good_matches: list[dict[str, Any]] = Field(default_factory=list)
    known_risk_matches: list[dict[str, Any]] = Field(default_factory=list)
    memory_confidence_adjustment: float = 0.0
    dependency_edges: list[DependencyEdge] = Field(default_factory=list)
    download_results: list[dict[str, Any]] = Field(default_factory=list)
    hash_verification_results: list[dict[str, Any]] = Field(default_factory=list)
    generated_artifacts: list[BuildArtifact] = Field(default_factory=list)
    artifacts: list[BuildArtifact] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    output_dir: str | None = None
    removed_mods: list[RemovedSelectedMod] = Field(default_factory=list)
    final_artifact_validation_status: str | None = None
    final_artifact_validation_report_path: str | None = None
    final_artifact_validation_summary: str | None = None
    content_sections: dict[str, Any] = Field(default_factory=dict)
