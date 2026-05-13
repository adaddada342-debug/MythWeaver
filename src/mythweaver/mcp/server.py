from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mythweaver.autopilot.contracts import AutopilotRequest
from mythweaver.autopilot.loop import run_autopilot
from mythweaver.core.settings import get_settings
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


def tool_definitions() -> list[dict[str, Any]]:
    candidate_array_schema = {"type": "array", "items": CandidateMod.model_json_schema()}
    return [
        {
            "name": "run_autopilot",
            "description": "Canonical backend operation: resolve, build, verify with private runtime proof, diagnose, safely repair, and return an agent-readable AutopilotReport.",
            "input_schema": AutopilotRequest.model_json_schema(),
        },
        {
            "name": "get_autopilot_run",
            "description": "Read a durable Autopilot run report and timeline summary from a runs/<run_id> artifact folder.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "output_root": {"type": ["string", "null"]},
                },
                "required": ["run_id"],
            },
        },
        {
            "name": "search_mods",
            "description": "Search Modrinth with agent-oriented installability metadata.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "loader": {"type": "string", "default": "fabric"},
                    "minecraft_version": {"type": "string", "default": "auto"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        },
        {
            "name": "inspect_mod",
            "description": "Inspect a Modrinth project and compatible versions/files.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "identifier": {"type": "string"},
                    "loader": {"type": "string", "default": "fabric"},
                    "minecraft_version": {"type": "string", "default": "auto"},
                },
                "required": ["identifier"],
            },
        },
        {
            "name": "compare_mods",
            "description": "Compare Modrinth candidates for a target loader/version.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "identifiers": {"type": "array", "items": {"type": "string"}},
                    "loader": {"type": "string", "default": "fabric"},
                    "minecraft_version": {"type": "string", "default": "auto"},
                },
                "required": ["identifiers"],
            },
        },
        {
            "name": "verify_mod_list",
            "description": "Verify an agent-selected mod list.",
            "input_schema": SelectedModList.model_json_schema(),
        },
        {
            "name": "resolve_mod_list",
            "description": "Resolve dependencies for an agent-selected mod list.",
            "input_schema": SelectedModList.model_json_schema(),
        },
        {
            "name": "build_from_list",
            "description": "Build/export from an agent-selected mod list.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "selected": SelectedModList.model_json_schema(),
                    "output_dir": {"type": "string"},
                    "download": {"type": "boolean", "default": True},
                    "validate_launch": {"type": "boolean", "default": False},
                },
                "required": ["selected", "output_dir"],
            },
        },
        {
            "name": "export_pack",
            "description": "Export a selected-list pack.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "selected": SelectedModList.model_json_schema(),
                    "output_dir": {"type": "string"},
                    "download": {"type": "boolean", "default": True},
                    "validate_launch": {"type": "boolean", "default": False},
                },
                "required": ["selected", "output_dir"],
            },
        },
        {
            "name": "validate_pack",
            "description": "Collect logs and optionally validate a generated pack through Prism.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pack_dir": {"type": "string"},
                    "pack_name": {"type": ["string", "null"]},
                    "instance_id": {"type": ["string", "null"]},
                },
                "required": ["pack_dir"],
            },
        },
        {
            "name": "create_repair_plan",
            "description": "Diagnose a failed pack validation and write repair options.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pack_dir": {"type": ["string", "null"]},
                    "report_path": {"type": ["string", "null"]},
                },
            },
        },
        {
            "name": "apply_repair_option",
            "description": "Apply one selected repair option to a copy of selected_mods.json.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repair_report": {"type": "string"},
                    "option_id": {"type": "string"},
                    "selected_mods": {"type": "string"},
                    "output": {"type": "string"},
                },
                "required": ["repair_report", "option_id", "selected_mods", "output"],
            },
        },
        {
            "name": "search_modrinth",
            "description": "Search verified Modrinth projects.",
            "input_schema": SearchPlan.model_json_schema(),
        },
        {
            "name": "analyze_mods",
            "description": "Summarize verified mod candidates.",
            "input_schema": {
                "type": "object",
                "properties": {"candidates": candidate_array_schema},
                "required": ["candidates"],
            },
        },
        {
            "name": "score_candidates",
            "description": "Score candidates against structured pack requirements.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "profile": RequirementProfile.model_json_schema(),
                    "candidates": candidate_array_schema,
                },
                "required": ["profile", "candidates"],
            },
        },
        {
            "name": "resolve_dependencies",
            "description": "Resolve required dependency graph.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "profile": RequirementProfile.model_json_schema(),
                    "requested_project_ids": {"type": "array", "items": {"type": "string"}},
                    "candidates": candidate_array_schema,
                    "loader_version": {"type": ["string", "null"]},
                },
                "required": ["profile", "requested_project_ids", "candidates"],
            },
        },
        {
            "name": "detect_conflicts",
            "description": "Detect duplicate functionality groups.",
            "input_schema": {
                "type": "object",
                "properties": {"candidates": candidate_array_schema},
                "required": ["candidates"],
            },
        },
        {
            "name": "build_pack",
            "description": "Build .mrpack artifact.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pack": ResolvedPack.model_json_schema(),
                    "output_dir": {"type": "string"},
                    "download": {"type": "boolean", "default": True},
                },
                "required": ["pack", "output_dir"],
            },
        },
        {
            "name": "generate_configs",
            "description": "Generate verified datapack/resource content.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "profile": RequirementProfile.model_json_schema(),
                    "output_dir": {"type": "string"},
                },
                "required": ["profile", "output_dir"],
            },
        },
        {
            "name": "validate_launch",
            "description": "Launch through Prism when configured.",
            "input_schema": {
                "type": "object",
                "properties": {"instance_id": {"type": "string"}},
                "required": ["instance_id"],
            },
        },
        {
            "name": "analyze_failure",
            "description": "Classify Minecraft crash or log output.",
            "input_schema": {
                "type": "object",
                "properties": {"log_text": {"type": "string"}},
                "required": ["log_text"],
            },
        },
        {
            "name": "generate_modpack",
            "description": "Run the end-to-end modpack generation pipeline.",
            "input_schema": GenerationRequest.model_json_schema(),
        },
        {
            "name": "plan_modpack_searches",
            "description": "Create deterministic Modrinth search plans from a profile.",
            "input_schema": RequirementProfile.model_json_schema(),
        },
        {
            "name": "discover_candidates",
            "description": "Search Modrinth and verify candidate versions/files.",
            "input_schema": SearchStrategy.model_json_schema(),
        },
        {
            "name": "expand_dependencies",
            "description": "Fetch missing required dependencies for candidates.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "candidates": candidate_array_schema,
                    "profile": RequirementProfile.model_json_schema(),
                    "minecraft_version": {"type": "string"},
                },
                "required": ["candidates", "profile", "minecraft_version"],
            },
        },
    ]


async def call_tool(facade: AgentToolFacade, name: str, arguments: dict[str, Any]) -> Any:
    if name == "run_autopilot":
        return await run_autopilot(AutopilotRequest.model_validate(arguments))
    if name == "get_autopilot_run":
        return _read_autopilot_run(arguments["run_id"], arguments.get("output_root"))
    if name == "search_mods":
        return await facade.search_mods(**arguments)
    if name == "inspect_mod":
        identifier = arguments.pop("identifier")
        return await facade.inspect_mod(identifier, **arguments)
    if name == "compare_mods":
        identifiers = arguments.pop("identifiers")
        return await facade.compare_mods(identifiers, **arguments)
    if name == "verify_mod_list":
        return await facade.verify_mod_list(SelectedModList.model_validate(arguments))
    if name == "resolve_mod_list":
        return await facade.resolve_mod_list(SelectedModList.model_validate(arguments))
    if name == "build_from_list":
        return await facade.build_from_list(
            SelectedModList.model_validate(arguments["selected"]),
            Path(arguments["output_dir"]),
            download=arguments.get("download", True),
            validate_launch=arguments.get("validate_launch", False),
        )
    if name == "export_pack":
        return await facade.export_pack(
            SelectedModList.model_validate(arguments["selected"]),
            Path(arguments["output_dir"]),
            download=arguments.get("download", True),
            validate_launch=arguments.get("validate_launch", False),
        )
    if name == "validate_pack":
        return await facade.validate_pack(
            Path(arguments["pack_dir"]),
            pack_name=arguments.get("pack_name"),
            instance_id=arguments.get("instance_id"),
        )
    if name == "create_repair_plan":
        return await facade.create_repair_plan(
            pack_dir=Path(arguments["pack_dir"]) if arguments.get("pack_dir") else None,
            report_path=Path(arguments["report_path"]) if arguments.get("report_path") else None,
        )
    if name == "apply_repair_option":
        return await facade.apply_repair_option(
            Path(arguments["repair_report"]),
            option_id=arguments["option_id"],
            selected_mods_path=Path(arguments["selected_mods"]),
            output_path=Path(arguments["output"]),
        )
    if name == "search_modrinth":
        return await facade.search_modrinth(SearchPlan.model_validate(arguments))
    if name == "analyze_mods":
        return facade.analyze_mods([CandidateMod.model_validate(item) for item in arguments["candidates"]])
    if name == "score_candidates":
        return facade.score_candidates(
            [CandidateMod.model_validate(item) for item in arguments["candidates"]],
            RequirementProfile.model_validate(arguments["profile"]),
        )
    if name == "resolve_dependencies":
        return facade.resolve_dependencies(
            arguments["requested_project_ids"],
            [CandidateMod.model_validate(item) for item in arguments["candidates"]],
            RequirementProfile.model_validate(arguments["profile"]),
            arguments.get("loader_version"),
        )
    if name == "detect_conflicts":
        return facade.detect_conflicts([CandidateMod.model_validate(item) for item in arguments["candidates"]])
    if name == "build_pack":
        return await facade.build_pack(
            ResolvedPack.model_validate(arguments["pack"]),
            Path(arguments["output_dir"]),
            download=arguments.get("download", True),
        )
    if name == "generate_configs":
        return facade.generate_configs(
            RequirementProfile.model_validate(arguments["profile"]),
            Path(arguments["output_dir"]),
        )
    if name == "validate_launch":
        return facade.validate_launch(arguments["instance_id"])
    if name == "analyze_failure":
        return facade.analyze_failure(arguments["log_text"])
    if name == "generate_modpack":
        return await facade.generate_modpack(GenerationRequest.model_validate(arguments))
    if name == "plan_modpack_searches":
        return facade.plan_modpack_searches(RequirementProfile.model_validate(arguments))
    if name == "discover_candidates":
        result = await facade.discover_candidates(SearchStrategy.model_validate(arguments))
        return {
            "candidates": result.candidates,
            "rejected": result.rejected,
            "minecraft_version": result.minecraft_version,
            "hits": result.hits,
        }
    if name == "expand_dependencies":
        candidates, rejected = await facade.expand_dependencies(
            [CandidateMod.model_validate(item) for item in arguments["candidates"]],
            RequirementProfile.model_validate(arguments["profile"]),
            arguments["minecraft_version"],
        )
        return {"candidates": candidates, "rejected": rejected}
    raise ValueError(f"unknown tool: {name}")


def _read_autopilot_run(run_id: str, output_root: str | None) -> dict[str, Any]:
    root = Path(output_root or Path.cwd() / ".test-output" / "autopilot") / "runs" / run_id
    report_path = root / "autopilot_report.json"
    timeline_path = root / "timeline.jsonl"
    if not report_path.is_file():
        raise FileNotFoundError(f"Autopilot run report not found: {report_path}")
    timeline_tail: list[dict[str, Any]] = []
    if timeline_path.is_file():
        lines = timeline_path.read_text(encoding="utf-8").splitlines()
        timeline_tail = [json.loads(line) for line in lines[-20:] if line.strip()]
    return {
        "run_id": run_id,
        "run_dir": str(root),
        "report": json.loads(report_path.read_text(encoding="utf-8")),
        "timeline_path": str(timeline_path) if timeline_path.is_file() else None,
        "timeline_tail": timeline_tail,
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


async def serve_stdio() -> None:
    """Serve a small JSON-RPC-compatible MCP-style protocol over stdin/stdout."""

    facade = AgentToolFacade(get_settings())
    for line in sys.stdin:
        request = json.loads(line)
        request_id = request.get("id")
        method = request.get("method")
        try:
            if method in {"tools/list", "list_tools"}:
                result = {"tools": tool_definitions()}
            elif method in {"tools/call", "call_tool"}:
                params = request.get("params", {})
                result = await call_tool(
                    facade,
                    params["name"],
                    params.get("arguments", {}),
                )
            else:
                raise ValueError(f"unsupported method: {method}")
            response = {"jsonrpc": "2.0", "id": request_id, "result": _jsonable(result)}
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(exc)},
            }
        print(json.dumps(response), flush=True)


def main() -> int:
    asyncio.run(serve_stdio())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
