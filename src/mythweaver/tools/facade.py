from __future__ import annotations

from pathlib import Path
from typing import Any

from mythweaver.builders.downloader import download_mod_file
from mythweaver.builders.mrpack import build_mrpack
from mythweaver.builders.paths import safe_file_name, safe_slug
from mythweaver.builders.prism_instance import build_prism_instance
from mythweaver.catalog.scoring import score_candidates
from mythweaver.configs.datapack import generate_lore_datapack
from mythweaver.core.settings import Settings
from mythweaver.db.cache import SQLiteCache
from mythweaver.modrinth.client import ModrinthClient
from mythweaver.pipeline.agent_service import AgentModpackService
from mythweaver.pipeline.dependencies import expand_required_dependencies
from mythweaver.pipeline.discovery import discover_candidates
from mythweaver.pipeline.service import GenerationPipeline
from mythweaver.pipeline.strategy import build_search_strategy
from mythweaver.resolver.engine import resolve_pack
from mythweaver.schemas.contracts import (
    BuildArtifact,
    CandidateMod,
    FailureAnalysis,
    GenerationReport,
    GenerationRequest,
    Loader,
    PackDesign,
    RequirementProfile,
    ResolvedPack,
    SearchPlan,
    SearchStrategy,
    SelectedModList,
    ValidationReport,
)
from mythweaver.validation.crash_analyzer import analyze_failure
from mythweaver.validation.prism import validate_launch


class AgentToolFacade:
    """One dependency-injectable facade shared by REST, CLI, TUI, and MCP."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.cache = SQLiteCache(self.settings.cache_db)
        self.modrinth = ModrinthClient(
            base_url=self.settings.modrinth_base_url,
            user_agent=self.settings.modrinth_user_agent,
            cache=self.cache,
        )
        self.last_final_artifact_validation_report: dict[str, Any] | None = None
        self.last_final_artifact_validation_ok: bool = True

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {"name": "search_mods", "description": "Search Modrinth with agent-oriented installability metadata."},
            {"name": "inspect_mod", "description": "Inspect a Modrinth project and compatible files."},
            {"name": "compare_mods", "description": "Compare Modrinth candidates for a target loader/version."},
            {"name": "verify_mod_list", "description": "Verify an agent-selected mod list."},
            {"name": "review_mod_list", "description": "Review selected_mods.json quality before build."},
            {"name": "agent_check", "description": "Create an AI-agent backend verification report for selected_mods.json."},
            {"name": "source_search", "description": "Search configured mod sources with acquisition safety metadata."},
            {"name": "source_inspect", "description": "Inspect one source ref such as modrinth:chipped or local:C:/mods/mod.jar."},
            {"name": "source_resolve", "description": "Resolve selected_mods.json across allowed sources and export policy."},
            {"name": "analyze_crash", "description": "Analyze a Minecraft runtime crash report for repairable mod/dependency failures."},
            {"name": "launch_check", "description": "Make launch/world-join validation explicit; dry-run is not playable proof."},
            {"name": "stabilize_pack", "description": "Run verification, dry-run, launch/crash analysis, and safe runtime repairs."},
            {"name": "setup_launcher", "description": "Create/import or validate a launcher instance without faking success."},
            {"name": "autonomous_build", "description": "Run backend build, launcher setup, launch-check, and safe runtime repair loop."},
            {"name": "design_pack", "description": "Create a deterministic pack design blueprint from a concept."},
            {"name": "review_pack_design", "description": "Review a pack design blueprint before mod selection."},
            {"name": "blueprint_pack", "description": "Generate deterministic mod selection slots from a pack design."},
            {"name": "resolve_mod_list", "description": "Hydrate and resolve dependencies for a selected mod list."},
            {"name": "build_from_list", "description": "Build .mrpack and Prism artifacts from a selected list."},
            {"name": "export_pack", "description": "Export a resolved selected-list pack."},
            {"name": "validate_pack", "description": "Collect logs and optionally validate a generated pack through Prism."},
            {"name": "create_repair_plan", "description": "Diagnose launch failure and write repair options."},
            {"name": "apply_repair_option", "description": "Apply one selected repair option to a copy of selected_mods.json."},
            {"name": "search_modrinth", "description": "Search verified Modrinth projects."},
            {"name": "analyze_mods", "description": "Summarize verified mod candidates."},
            {"name": "score_candidates", "description": "Score candidate mods deterministically."},
            {"name": "resolve_dependencies", "description": "Resolve required dependency graph."},
            {"name": "detect_conflicts", "description": "Detect duplicate capability groups."},
            {"name": "build_pack", "description": "Build Prism instance metadata and .mrpack."},
            {"name": "generate_configs", "description": "Apply verified generated content recipes."},
            {"name": "validate_launch", "description": "Launch through Prism when configured."},
            {"name": "analyze_failure", "description": "Classify Minecraft crash or log output."},
            {"name": "generate_modpack", "description": "Run the end-to-end generation pipeline."},
            {"name": "plan_modpack_searches", "description": "Create search plans from a profile."},
            {"name": "discover_candidates", "description": "Search Modrinth and verify candidates."},
            {"name": "expand_dependencies", "description": "Fetch missing required dependencies."},
        ]

    def agent_service(self) -> AgentModpackService:
        return AgentModpackService(self)

    async def search_mods(self, query: str, **filters):
        return await self.agent_service().search_mods(query, **filters)

    async def inspect_mod(self, identifier: str, **filters):
        return await self.agent_service().inspect_mod(identifier, **filters)

    async def compare_mods(self, identifiers: list[str], **filters):
        return await self.agent_service().compare_mods(identifiers, **filters)

    async def verify_mod_list(self, selected: SelectedModList):
        return await self.agent_service().verify_mod_list(selected)

    async def review_mod_list(
        self,
        selected: SelectedModList,
        output_dir: Path | None = None,
        *,
        write_prompt: bool = True,
        pack_design: PackDesign | None = None,
        pack_design_path: Path | str | None = None,
    ):
        return await self.agent_service().review_mod_list(
            selected,
            output_dir,
            write_prompt=write_prompt,
            pack_design=pack_design,
            pack_design_path=pack_design_path,
        )

    async def agent_check(
        self,
        selected: SelectedModList,
        output_dir: Path | None = None,
        *,
        write_prompt: bool = True,
        pack_design: PackDesign | None = None,
        pack_design_path: Path | str | None = None,
        sources: list[str] | None = None,
        target_export: str = "modrinth_pack",
        allow_manual_sources: bool = False,
    ):
        return await self.agent_service().agent_check(
            selected,
            output_dir,
            write_prompt=write_prompt,
            pack_design=pack_design,
            pack_design_path=pack_design_path,
            sources=sources,
            target_export=target_export,
            allow_manual_sources=allow_manual_sources,
        )

    async def source_search(
        self,
        query: str,
        *,
        minecraft_version: str,
        loader: str,
        sources: list[str] | None = None,
        limit: int = 20,
        output_dir: Path | None = None,
    ):
        return await self.agent_service().source_search(
            query,
            minecraft_version=minecraft_version,
            loader=loader,
            sources=sources,
            limit=limit,
            output_dir=output_dir,
        )

    async def source_inspect(
        self,
        source_ref: str,
        *,
        minecraft_version: str,
        loader: str,
        output_dir: Path | None = None,
    ):
        return await self.agent_service().source_inspect(
            source_ref,
            minecraft_version=minecraft_version,
            loader=loader,
            output_dir=output_dir,
        )

    async def source_resolve(
        self,
        selected: SelectedModList,
        *,
        sources: list[str] | None = None,
        target_export: str = "local_instance",
        autonomous: bool = True,
        allow_manual_sources: bool = False,
        output_dir: Path | None = None,
    ):
        return await self.agent_service().resolve_sources(
            selected,
            sources=sources,
            target_export=target_export,
            autonomous=autonomous,
            allow_manual_sources=allow_manual_sources,
            output_dir=output_dir,
        )

    async def analyze_crash(
        self,
        crash_text: str,
        *,
        selected: SelectedModList | None = None,
        selected_mods_path: str | None = None,
        crash_report_path: str | None = None,
        output_dir: Path | None = None,
    ):
        return await self.agent_service().analyze_crash(
            crash_text,
            selected=selected,
            selected_mods_path=selected_mods_path,
            crash_report_path=crash_report_path,
            output_dir=output_dir,
        )

    async def launch_check(
        self,
        selected: SelectedModList,
        pack_dir: Path,
        *,
        manual: bool = False,
        crash_report: Path | None = None,
    ):
        return await self.agent_service().launch_check(selected, pack_dir, manual=manual, crash_report=crash_report)

    async def stabilize_pack(
        self,
        selected: SelectedModList,
        output_dir: Path,
        *,
        pack_design: PackDesign | None = None,
        pack_design_path: Path | str | None = None,
        max_attempts: int = 3,
        manual_crash_report: Path | None = None,
        no_launch: bool = False,
        prefer_remove_risky_optionals: bool = True,
    ):
        return await self.agent_service().stabilize_pack(
            selected,
            output_dir,
            pack_design=pack_design,
            pack_design_path=pack_design_path,
            max_attempts=max_attempts,
            manual_crash_report=manual_crash_report,
            no_launch=no_launch,
            prefer_remove_risky_optionals=prefer_remove_risky_optionals,
        )

    async def setup_launcher(self, pack_artifact: Path, output_dir: Path, **kwargs):
        return await self.agent_service().setup_launcher(pack_artifact, output_dir, **kwargs)

    async def launcher_launch_check(self, **kwargs):
        return await self.agent_service().launcher_launch_check(**kwargs)

    async def autonomous_build(self, concept_path: Path, output_dir: Path, **kwargs):
        return await self.agent_service().autonomous_build(concept_path, output_dir, **kwargs)

    def design_pack(
        self,
        concept_text: str,
        *,
        output_dir: Path | None = None,
        name: str | None = None,
        minecraft_version: str = "1.20.1",
        loader: Loader = "fabric",
        write_prompt: bool = True,
    ):
        return self.agent_service().design_pack_from_concept(
            concept_text,
            output_dir=output_dir,
            name=name,
            minecraft_version=minecraft_version,
            loader=loader,
            write_prompt=write_prompt,
        )

    def review_pack_design(
        self,
        design: PackDesign,
        *,
        output_dir: Path | None = None,
        write_prompt: bool = True,
    ):
        return self.agent_service().review_pack_design(design, output_dir=output_dir, write_prompt=write_prompt)

    def blueprint_pack(
        self,
        design: PackDesign,
        *,
        design_path: Path | None = None,
        output_dir: Path | None = None,
        write_prompt: bool = True,
    ):
        return self.agent_service().blueprint_pack_from_design(
            design,
            design_path=design_path,
            output_dir=output_dir,
            write_prompt=write_prompt,
        )

    async def resolve_mod_list(self, selected: SelectedModList):
        return await self.agent_service().resolve_mod_list(selected)

    async def build_from_list(
        self,
        selected: SelectedModList,
        output_dir: Path,
        *,
        download: bool = True,
        validate_launch: bool = False,
        force: bool = False,
        loader_version: str | None = None,
        memory_mb: int | None = None,
        sources: list[str] | None = None,
        target_export: str | None = None,
        auto_target: bool = False,
        candidate_versions: list[str] | None = None,
        candidate_loaders: list[str] | None = None,
        allow_manual_sources: bool = False,
    ):
        return await self.agent_service().build_from_list(
            selected,
            output_dir,
            download=download,
            validate_launch=validate_launch,
            force=force,
            loader_version=loader_version,
            memory_mb=memory_mb,
            sources=sources,
            target_export=target_export,
            auto_target=auto_target,
            candidate_versions=candidate_versions,
            candidate_loaders=candidate_loaders,
            allow_manual_sources=allow_manual_sources,
        )

    async def export_pack(self, selected: SelectedModList, output_dir: Path, *, download: bool = True, validate_launch: bool = False, force: bool = False):
        return await self.build_from_list(selected, output_dir, download=download, validate_launch=validate_launch, force=force)

    async def validate_pack(
        self,
        pack_dir: Path,
        *,
        pack_name: str | None = None,
        instance_id: str | None = None,
        force_validation: bool = True,
        check_config_only: bool = False,
    ):
        return await self.agent_service().validate_pack(
            pack_dir,
            pack_name=pack_name,
            instance_id=instance_id,
            force_validation=force_validation,
            check_config_only=check_config_only,
        )

    async def create_repair_plan(self, pack_dir: Path | None = None, *, report_path: Path | None = None):
        return await self.agent_service().create_repair_plan(pack_dir, report_path=report_path)

    async def apply_repair_option(
        self,
        repair_report_path: Path,
        *,
        option_id: str,
        selected_mods_path: Path,
        output_path: Path,
    ):
        return await self.agent_service().apply_repair_option(
            repair_report_path,
            option_id=option_id,
            selected_mods_path=selected_mods_path,
            output_path=output_path,
        )

    async def search_modrinth(self, plan: SearchPlan) -> dict:
        return await self.modrinth.search_projects(plan)

    def analyze_mods(self, candidates: list[CandidateMod]) -> list[dict[str, object]]:
        return [
            {
                "project_id": candidate.project_id,
                "title": candidate.title,
                "version": candidate.selected_version.version_number,
                "loader": candidate.selected_version.loaders,
                "minecraft_versions": candidate.selected_version.game_versions,
                "dependencies": [
                    dependency.model_dump()
                    for dependency in candidate.selected_version.dependencies
                ],
                "downloads": candidate.downloads,
                "side_support": {
                    "client": candidate.client_side,
                    "server": candidate.server_side,
                },
            }
            for candidate in candidates
        ]

    def score_candidates(
        self, candidates: list[CandidateMod], profile: RequirementProfile
    ) -> list[CandidateMod]:
        return score_candidates(candidates, profile)

    def resolve_dependencies(
        self,
        requested_project_ids: list[str],
        candidates: list[CandidateMod],
        profile: RequirementProfile,
        loader_version: str | None = None,
    ) -> ResolvedPack:
        return resolve_pack(requested_project_ids, candidates, profile, loader_version)

    def detect_conflicts(self, candidates: list[CandidateMod]) -> list[dict[str, object]]:
        buckets: dict[str, list[str]] = {}
        capability_groups = {
            "performance": {"optimization", "performance"},
            "renderer_optimization": {"sodium", "embeddium", "rubidium"},
            "shader_loader": {"iris", "oculus"},
            "worldgen": {"worldgen", "biomes"},
            "mobs": {"mobs", "creatures"},
            "magic": {"magic"},
            "quests": {"quests"},
            "storage": {"storage"},
            "maps": {"map", "utility"},
        }
        for candidate in candidates:
            categories = set(candidate.categories)
            text = candidate.searchable_text()
            for group, markers in capability_groups.items():
                if categories & markers or any(marker in text for marker in markers):
                    buckets.setdefault(group, []).append(candidate.project_id)
        return [
            {
                "group": group,
                "project_ids": project_ids,
                "reason": "duplicate_functionality",
            }
            for group, project_ids in sorted(buckets.items())
            if len(project_ids) > 1
        ]

    async def build_pack(
        self,
        pack: ResolvedPack,
        output_dir: Path,
        *,
        download: bool = True,
        memory_mb: int | None = None,
        artifact_prefer_project_ids: frozenset[str] | None = None,
    ) -> list[BuildArtifact]:
        from mythweaver.validation.final_artifact_validation import validate_and_filter_resolved_pack, write_final_report

        output_dir.mkdir(parents=True, exist_ok=True)
        self.last_final_artifact_validation_ok = True
        self.last_final_artifact_validation_report = None

        artifact_report_path = output_dir / "final_artifact_validation_report.json"

        export_pack = pack
        export_downloaded: dict[str, Path] | None = None

        if download:
            downloaded_files: dict[str, Path] = {}
            cache_root = output_dir / "cache" / "mods"
            for mod in pack.selected_mods:
                file = mod.primary_file()
                destination = cache_root / safe_file_name(mod.project_id) / safe_file_name(file.filename)
                downloaded_files[mod.project_id] = await download_mod_file(
                    file,
                    destination,
                    self.settings.modrinth_user_agent,
                )
            export_pack, filtered_files, art_report, art_ok = validate_and_filter_resolved_pack(
                pack,
                downloaded_files,
                prefer_project_ids=artifact_prefer_project_ids or frozenset(),
                target_minecraft=pack.minecraft_version,
            )
            self.last_final_artifact_validation_report = art_report
            self.last_final_artifact_validation_ok = art_ok and art_report.get("status") != "failed"
            write_final_report(artifact_report_path, art_report)

            if not self.last_final_artifact_validation_ok:
                vr = BuildArtifact(
                    kind="final-artifact-validation-report",
                    path=str(artifact_report_path),
                    metadata={"status": "failed"},
                )
                return [vr]

            export_downloaded = filtered_files
        else:
            skipped_report = {
                "status": "skipped",
                "detail": "download_disabled_no_jars_to_validate",
                "final_mod_count": len(pack.selected_mods),
            }
            write_final_report(artifact_report_path, skipped_report)
            self.last_final_artifact_validation_report = skipped_report

        artifacts: list[BuildArtifact] = [build_mrpack(export_pack, output_dir / f"{_slug(pack.name)}.mrpack")]
        if download and export_downloaded is not None:
            artifacts.append(
                build_prism_instance(
                    export_pack,
                    output_dir / "instances",
                    downloaded_files=export_downloaded,
                    memory_mb=memory_mb,
                )
            )
        artifacts.insert(
            0,
            BuildArtifact(
                kind="final-artifact-validation-report",
                path=str(artifact_report_path),
                metadata={"status": (self.last_final_artifact_validation_report or {}).get("status") or ("skipped" if not download else "passed")},
            ),
        )
        return artifacts

    def generate_configs(self, profile: RequirementProfile, output_dir: Path) -> BuildArtifact:
        return generate_lore_datapack(profile, output_dir)

    def validate_launch(self, instance_id: str) -> ValidationReport:
        return validate_launch(instance_id, self.settings)

    def analyze_failure(self, log_text: str) -> FailureAnalysis:
        return analyze_failure(log_text)

    async def generate_modpack(self, request: GenerationRequest) -> GenerationReport:
        return await GenerationPipeline(self).generate(request)

    def plan_modpack_searches(self, profile: RequirementProfile, limit: int = 20) -> SearchStrategy:
        return build_search_strategy(profile, limit=limit)

    async def discover_candidates(self, strategy: SearchStrategy):
        return await discover_candidates(self.modrinth, strategy)

    async def expand_dependencies(
        self,
        candidates: list[CandidateMod],
        profile: RequirementProfile,
        minecraft_version: str,
    ):
        return await expand_required_dependencies(self.modrinth, candidates, profile, minecraft_version)


def _slug(value: str) -> str:
    return safe_slug(value, fallback="mythweaver-pack")
