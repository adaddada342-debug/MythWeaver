from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from mythweaver.autopilot.contracts import AutopilotRequest
from mythweaver.autopilot.loop import run_autopilot
from mythweaver.core.settings import Settings
from mythweaver.schemas.contracts import (
    CandidateMod,
    GenerationRequest,
    RequirementProfile,
    ResolvedPack,
    SearchPlan,
    SearchStrategy,
    SelectedModList,
)
from mythweaver.tools.facade import AgentToolFacade


class ScoreRequest(BaseModel):
    profile: RequirementProfile
    candidates: list[CandidateMod]


class ResolveRequest(BaseModel):
    profile: RequirementProfile
    requested_project_ids: list[str]
    candidates: list[CandidateMod]
    loader_version: str | None = None


class ConflictRequest(BaseModel):
    candidates: list[CandidateMod]


class BuildRequest(BaseModel):
    pack: ResolvedPack
    output_dir: str
    download: bool = True


class ConfigRequest(BaseModel):
    profile: RequirementProfile
    output_dir: str


class FailureRequest(BaseModel):
    log_text: str


class LaunchRequest(BaseModel):
    instance_id: str


class DependencyExpansionRequest(BaseModel):
    candidates: list[CandidateMod]
    profile: RequirementProfile
    minecraft_version: str


class AgentSearchRequest(BaseModel):
    query: str
    loader: str = "fabric"
    minecraft_version: str = "auto"
    limit: int = 20
    include: list[str] = []
    exclude: list[str] = []
    capability: list[str] = []
    role: str | None = None
    client: str | None = None
    server: str | None = None
    min_downloads: int = 0
    sort: str = "relevance"


class AgentInspectRequest(BaseModel):
    identifier: str
    loader: str = "fabric"
    minecraft_version: str = "auto"


class AgentCompareRequest(BaseModel):
    identifiers: list[str]
    loader: str = "fabric"
    minecraft_version: str = "auto"


class AgentBuildRequest(BaseModel):
    selected: SelectedModList
    output_dir: str
    download: bool = True
    validate_launch: bool = False


class ValidatePackRequest(BaseModel):
    pack_dir: str
    pack_name: str | None = None
    instance_id: str | None = None


class RepairPlanRequest(BaseModel):
    pack_dir: str | None = None
    report_path: str | None = None


class ApplyRepairRequest(BaseModel):
    repair_report: str
    option_id: str
    selected_mods: str
    output: str


def create_app(settings: Settings | None = None):
    """Create the FastAPI app.

    FastAPI is an install dependency, but imports are lazy so core tests and CLI helpers can run in
    minimal local Python environments.
    """

    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise RuntimeError("FastAPI is not installed. Run `pip install -e .` first.") from exc

    facade = AgentToolFacade(settings=settings)
    app = FastAPI(
        title="MythWeaver",
        version="0.1.0",
        description="Agent-first local Minecraft modpack intelligence service.",
    )

    @app.get("/v1/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "ai_required": False, "ai_enabled": facade.settings.ai_enabled}

    @app.get("/v1/tools")
    def tools() -> list[dict[str, str]]:
        return facade.list_tools()

    @app.post("/v1/autopilot/run")
    async def autopilot_run(request: AutopilotRequest):
        return await run_autopilot(request)

    @app.get("/v1/autopilot/runs/{run_id}")
    def autopilot_run_status(run_id: str, output_root: str | None = None):
        from fastapi import HTTPException

        root = Path(output_root or Path.cwd() / ".test-output" / "autopilot") / "runs" / run_id
        report_path = root / "autopilot_report.json"
        timeline_path = root / "timeline.jsonl"
        if not report_path.is_file():
            raise HTTPException(status_code=404, detail={"kind": "autopilot_run_not_found", "run_id": run_id})
        timeline_tail: list[dict[str, object]] = []
        if timeline_path.is_file():
            timeline_tail = [json.loads(line) for line in timeline_path.read_text(encoding="utf-8").splitlines()[-20:] if line.strip()]
        return {
            "run_id": run_id,
            "run_dir": str(root),
            "report": json.loads(report_path.read_text(encoding="utf-8")),
            "timeline_path": str(timeline_path) if timeline_path.is_file() else None,
            "timeline_tail": timeline_tail,
        }

    @app.post("/v1/search_modrinth")
    async def search_modrinth(plan: SearchPlan):
        return await facade.search_modrinth(plan)

    @app.post("/v1/search_mods")
    async def search_mods(request: AgentSearchRequest):
        return await facade.search_mods(**request.model_dump())

    @app.post("/v1/inspect_mod")
    async def inspect_mod(request: AgentInspectRequest):
        return await facade.inspect_mod(request.identifier, loader=request.loader, minecraft_version=request.minecraft_version)

    @app.post("/v1/compare_mods")
    async def compare_mods(request: AgentCompareRequest):
        return await facade.compare_mods(request.identifiers, loader=request.loader, minecraft_version=request.minecraft_version)

    @app.post("/v1/verify_mod_list")
    async def verify_mod_list(selected: SelectedModList):
        return await facade.verify_mod_list(selected)

    @app.post("/v1/resolve_mod_list")
    async def resolve_mod_list(selected: SelectedModList):
        return await facade.resolve_mod_list(selected)

    @app.post("/v1/build_from_list")
    async def build_from_list(request: AgentBuildRequest):
        return await facade.build_from_list(
            request.selected,
            Path(request.output_dir),
            download=request.download,
            validate_launch=request.validate_launch,
        )

    @app.post("/v1/export_pack")
    async def export_pack(request: AgentBuildRequest):
        return await facade.export_pack(
            request.selected,
            Path(request.output_dir),
            download=request.download,
            validate_launch=request.validate_launch,
        )

    @app.post("/v1/validate_pack")
    async def validate_pack(request: ValidatePackRequest):
        return await facade.validate_pack(Path(request.pack_dir), pack_name=request.pack_name, instance_id=request.instance_id)

    @app.post("/v1/repair/plan")
    async def repair_plan(request: RepairPlanRequest):
        return await facade.create_repair_plan(
            Path(request.pack_dir) if request.pack_dir else None,
            report_path=Path(request.report_path) if request.report_path else None,
        )

    @app.post("/v1/repair/apply")
    async def repair_apply(request: ApplyRepairRequest):
        return await facade.apply_repair_option(
            Path(request.repair_report),
            option_id=request.option_id,
            selected_mods_path=Path(request.selected_mods),
            output_path=Path(request.output),
        )

    @app.post("/v1/analyze_mods")
    def analyze_mods(candidates: list[CandidateMod]):
        return facade.analyze_mods(candidates)

    @app.post("/v1/score_candidates")
    def score_candidates(request: ScoreRequest) -> list[CandidateMod]:
        return facade.score_candidates(request.candidates, request.profile)

    @app.post("/v1/resolve_dependencies")
    def resolve_dependencies(request: ResolveRequest) -> ResolvedPack:
        return facade.resolve_dependencies(
            request.requested_project_ids,
            request.candidates,
            request.profile,
            request.loader_version,
        )

    @app.post("/v1/detect_conflicts")
    def detect_conflicts(request: ConflictRequest):
        return facade.detect_conflicts(request.candidates)

    @app.post("/v1/build_pack")
    async def build_pack(request: BuildRequest):
        return await facade.build_pack(
            request.pack,
            Path(request.output_dir),
            download=request.download,
        )

    @app.post("/v1/generate_configs")
    def generate_configs(request: ConfigRequest):
        return facade.generate_configs(request.profile, Path(request.output_dir))

    @app.post("/v1/validate_launch")
    def validate_launch(request: LaunchRequest):
        return facade.validate_launch(request.instance_id)

    @app.post("/v1/analyze_failure")
    def analyze_failure(request: FailureRequest):
        return facade.analyze_failure(request.log_text)

    @app.post("/v1/generate")
    async def generate(request: GenerationRequest):
        return await facade.generate_modpack(request)

    @app.post("/v1/plan_modpack_searches")
    def plan_modpack_searches(profile: RequirementProfile):
        return facade.plan_modpack_searches(profile)

    @app.post("/v1/discover_candidates")
    async def discover_candidates(strategy: SearchStrategy):
        result = await facade.discover_candidates(strategy)
        return {
            "candidates": result.candidates,
            "rejected": result.rejected,
            "minecraft_version": result.minecraft_version,
            "hits": result.hits,
        }

    @app.post("/v1/expand_dependencies")
    async def expand_dependencies(request: DependencyExpansionRequest):
        candidates, rejected = await facade.expand_dependencies(
            request.candidates, request.profile, request.minecraft_version
        )
        return {"candidates": candidates, "rejected": rejected}

    return app


app = None
