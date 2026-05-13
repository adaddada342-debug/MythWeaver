from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mythweaver.api.app import create_app
from mythweaver.autopilot.contracts import AutopilotBlocker, AutopilotReport, AutopilotRequest
from mythweaver.autopilot.loop import run_autopilot
from mythweaver.builders.paths import safe_slug
from mythweaver.core.settings import get_settings
from mythweaver.handoff import (
    export_cloud_handoff_zip,
    import_selected_mods_file,
    validate_selected_mods_file,
    write_agent_workflow_prompt,
)
from mythweaver.onboarding import START_MESSAGE, write_agent_session
from mythweaver.schemas.contracts import GenerationRequest, PackDesign, RequirementProfile, SelectedModList
from mythweaver.tools.facade import AgentToolFacade


def _print_json(value: Any) -> None:
    value = _jsonable(value)
    print(json.dumps(value, indent=2, sort_keys=True))


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def exit_code_for_autopilot_report(report: AutopilotReport) -> int:
    blocker_kinds = {blocker.kind for blocker in report.blockers}
    if "invalid_request" in blocker_kinds:
        return 3
    if blocker_kinds & {"environment_missing_java", "java_runtime_missing", "runtime_setup_failed", "minecraft_client_prepare_failed"}:
        return 4
    if report.status == "verified_playable":
        return 0
    if report.status == "blocked":
        return 1
    if report.status in {"max_attempts_reached", "failed"}:
        return 2
    return 5


def _print_autopilot_human(report: AutopilotReport) -> None:
    print(f"MythWeaver Autopilot: {report.status.replace('_', ' ').upper()}")
    print(f"Run id: {report.run_id or 'n/a'}")
    if report.run_dir:
        print(f"Run dir: {report.run_dir}")
    print()
    print("Final target:")
    print(f"- Minecraft {report.final_minecraft_version or 'n/a'}")
    print(f"- Loader {report.final_loader or 'n/a'} {report.final_loader_version or ''}".rstrip())
    if report.final_proof is not None:
        print(f"- Proof {report.final_proof.proof_level}")
        print(f"- Smoke-test helper used {report.final_proof.smoke_test_mod_used}")
        print(f"- Stability seconds {report.final_proof.stability_seconds_proven}")
        print(f"- Evidence {report.final_proof.evidence_path or 'n/a'}")
    print()
    print("Attempts:")
    for attempt in report.attempts:
        issue_text = ", ".join(issue.kind for issue in attempt.issues) or "none"
        print(f"{attempt.attempt_number}. {attempt.runtime_status}: {issue_text}")
        for diagnosis in attempt.diagnoses:
            print(f"   Diagnosis: {diagnosis.kind} ({diagnosis.confidence}) - {diagnosis.summary}")
        for applied in attempt.actions_applied:
            print(f"   Applied: {applied.status} {applied.action.action} {applied.action.query or ''}".rstrip())
        for blocker in attempt.blockers:
            print(f"   Blocker: {blocker.kind} ({blocker.severity}) - {blocker.message}")
    if report.blockers:
        print()
        print("Blockers:")
        for blocker in report.blockers:
            print(f"- {blocker.kind} ({blocker.severity}): {blocker.message}")
            if blocker.suggested_next_step:
                print(f"  Next: {blocker.suggested_next_step}")
    print()
    print(f"Final instance: {report.final_instance_path or 'n/a'}")
    print(f"Timeline: {report.timeline_path or 'n/a'}")
    print(f"Report: {report.report_paths.get('json', 'n/a')}")


def _add_prism_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prism-executable-path")
    parser.add_argument("--prism-instances-path")
    parser.add_argument("--prism-account-name")
    parser.add_argument("--launch-timeout-seconds", type=int)
    parser.add_argument("--java-path")
    parser.add_argument("--validation-enabled", action="store_true")


def _add_source_build_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sources", help="Comma-separated source providers, such as modrinth,curseforge,local.")
    parser.add_argument(
        "--target-export",
        choices=["modrinth_pack", "curseforge_manifest", "prism_instance", "local_instance", "multimc_instance"],
        help="Source-aware export target. Omit to preserve the existing Modrinth-first build path.",
    )
    parser.add_argument("--auto-target", action="store_true", help="Negotiate Minecraft version and loader when selected_mods uses auto/any.")
    parser.add_argument("--candidate-versions", help="Comma-separated Minecraft versions to consider during --auto-target.")
    parser.add_argument("--candidate-loaders", help="Comma-separated loaders to consider during --auto-target.")
    parser.add_argument("--allow-manual-sources", action="store_true", help="Allow manual-required source metadata in reports where policy permits it.")


def _settings_for_args(args: argparse.Namespace, *, force_validation: bool = False):
    settings = get_settings()
    if getattr(args, "prism_executable_path", None):
        settings.prism_executable_path = args.prism_executable_path
    if getattr(args, "prism_instances_path", None):
        settings.prism_instances_path = Path(args.prism_instances_path)
    if getattr(args, "prism_account_name", None):
        settings.prism_account_name = args.prism_account_name
    if getattr(args, "launch_timeout_seconds", None) is not None:
        settings.launch_timeout_seconds = args.launch_timeout_seconds
    if getattr(args, "java_path", None):
        settings.java_path = args.java_path
    if force_validation or getattr(args, "validation_enabled", False):
        settings.validation_enabled = True
    return settings


def _fallback_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mythweaver")
    subcommands = parser.add_subparsers(dest="command", required=True)

    start = subcommands.add_parser("start", help="Start the friendly modpack idea flow.")
    start.add_argument("idea", nargs="*", help="Optional modpack idea. If omitted, prints the prompt.")
    start.add_argument(
        "--output-dir",
        default="output/generated/session",
        help="Where to write agent handoff files when an idea is provided.",
    )

    subcommands.add_parser("tools", help="List deterministic agent tools.")

    search = subcommands.add_parser("search", help="Search Modrinth for agent-curated candidates.")
    search.add_argument("query")
    search.add_argument("--minecraft", "--minecraft-version", dest="minecraft_version", default="auto")
    search.add_argument("--loader", default="fabric")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--include", action="append", default=[])
    search.add_argument("--exclude", action="append", default=[])
    search.add_argument("--capability", action="append", default=[])
    search.add_argument("--role")
    search.add_argument("--client")
    search.add_argument("--server")
    search.add_argument("--min-downloads", type=int, default=0)
    search.add_argument("--sort", default="relevance", choices=["relevance", "downloads", "follows", "updated"])

    inspect = subcommands.add_parser("inspect", help="Inspect a Modrinth mod.")
    inspect.add_argument("identifier")
    inspect.add_argument("--minecraft", "--minecraft-version", dest="minecraft_version", default="auto")
    inspect.add_argument("--loader", default="fabric")

    compare = subcommands.add_parser("compare", help="Compare Modrinth mods.")
    compare.add_argument("identifiers", nargs="+")
    compare.add_argument("--minecraft", "--minecraft-version", dest="minecraft_version", default="auto")
    compare.add_argument("--loader", default="fabric")

    verify_list = subcommands.add_parser("verify-list", help="Verify an agent-selected mod list JSON.")
    verify_list.add_argument("selected_mods")
    verify_list.add_argument("--minecraft", "--minecraft-version", dest="minecraft_version")
    verify_list.add_argument("--loader")

    review_list = subcommands.add_parser(
        "review-list",
        help="Review selected_mods.json quality before building.",
        description="Review selected_mods.json quality before building.",
    )
    review_list.add_argument("selected_mods")
    review_list.add_argument("--output", "--output-dir", dest="output_dir")
    review_list.add_argument("--no-prompt", action="store_true")
    review_list.add_argument("--against", dest="pack_design", help="Review against a pack_design.json blueprint.")
    review_list.add_argument("--sources", help="Comma-separated source providers to check, such as modrinth,curseforge,local.")
    review_list.add_argument("--target-export", default="modrinth_pack", choices=["modrinth_pack", "curseforge_manifest", "local_instance", "prism_instance"])
    review_list.add_argument("--allow-manual-sources", action="store_true")

    agent_check = subcommands.add_parser(
        "agent-check",
        help="Write an AI-agent backend verification report for selected_mods.json.",
        description="Write an AI-agent backend verification report for selected_mods.json.",
    )
    agent_check.add_argument("selected_mods")
    agent_check.add_argument("--against", dest="pack_design", help="Optional pack_design.json for advisory design signals.")
    agent_check.add_argument("--output", "--output-dir", dest="output_dir")
    agent_check.add_argument("--no-prompt", action="store_true")
    agent_check.add_argument("--sources", help="Comma-separated source providers to check, such as modrinth,curseforge,local.")
    agent_check.add_argument("--target-export", default="modrinth_pack", choices=["modrinth_pack", "curseforge_manifest", "local_instance", "prism_instance"])
    agent_check.add_argument("--allow-manual-sources", action="store_true")

    source_search = subcommands.add_parser("source-search", help="Search mod sources with acquisition safety metadata.")
    source_search.add_argument("query")
    source_search.add_argument("--mc-version", "--minecraft-version", dest="minecraft_version", required=True)
    source_search.add_argument("--loader", default="fabric")
    source_search.add_argument("--sources", default="modrinth")
    source_search.add_argument("--limit", type=int, default=20)
    source_search.add_argument("--output", "--output-dir", dest="output_dir")

    source_inspect = subcommands.add_parser("source-inspect", help="Inspect one source ref, e.g. modrinth:chipped or local:C:/mods/mod.jar.")
    source_inspect.add_argument("source_ref")
    source_inspect.add_argument("--mc-version", "--minecraft-version", dest="minecraft_version", required=True)
    source_inspect.add_argument("--loader", default="fabric")
    source_inspect.add_argument("--output", "--output-dir", dest="output_dir")

    source_resolve = subcommands.add_parser("source-resolve", help="Resolve selected_mods.json across allowed sources and export policy.")
    source_resolve.add_argument("selected_mods")
    source_resolve.add_argument("--mc-version", "--minecraft-version", dest="minecraft_version")
    source_resolve.add_argument("--loader")
    source_resolve.add_argument("--sources", default="modrinth")
    source_resolve.add_argument("--target-export", default="local_instance", choices=["modrinth_pack", "curseforge_manifest", "local_instance", "prism_instance"])
    source_resolve.add_argument("--allow-manual-sources", action="store_true")
    source_resolve.add_argument("--output", "--output-dir", dest="output_dir")

    agent_workflow = subcommands.add_parser(
        "agent-workflow-prompt",
        help="Write a Cursor/Codex workflow prompt for using MythWeaver as a backend.",
        description="Write a Cursor/Codex workflow prompt for using MythWeaver as a backend.",
    )
    agent_workflow.add_argument("concept")
    agent_workflow.add_argument("--output", "--output-dir", dest="output_dir")
    agent_workflow.add_argument("--name")

    design_pack = subcommands.add_parser(
        "design-pack",
        help="Design a deterministic modpack blueprint from a concept file.",
        description="Design a deterministic modpack blueprint from a concept file.",
    )
    design_pack.add_argument("concept")
    design_pack.add_argument("--output", "--output-dir", dest="output_dir")
    design_pack.add_argument("--name")
    design_pack.add_argument("--minecraft-version", default="1.20.1")
    design_pack.add_argument("--loader", default="fabric")

    review_design = subcommands.add_parser(
        "review-design",
        help="Review a pack_design.json blueprint.",
        description="Review a pack_design.json blueprint.",
    )
    review_design.add_argument("pack_design")
    review_design.add_argument("--output", "--output-dir", dest="output_dir")
    review_design.add_argument("--no-prompt", action="store_true")

    blueprint_pack = subcommands.add_parser(
        "blueprint-pack",
        help="Generate a deterministic mod selection blueprint from pack_design.json.",
        description="Generate a deterministic mod selection blueprint from pack_design.json.",
    )
    blueprint_pack.add_argument("pack_design")
    blueprint_pack.add_argument("--output", "--output-dir", dest="output_dir")
    blueprint_pack.add_argument("--no-prompt", action="store_true")

    resolve = subcommands.add_parser("resolve", help="Resolve dependencies for an agent-selected mod list JSON.")
    resolve.add_argument("selected_mods")

    build_list = subcommands.add_parser("build-from-list", help="Build from an agent-selected mod list JSON.")
    build_list.add_argument("selected_mods")
    build_list.add_argument("--output", "--output-dir", dest="output_dir")
    build_list.add_argument("--dry-run", action="store_true")
    build_list.add_argument("--validate-launch", action="store_true")
    build_list.add_argument("--force", action="store_true", help="Allow build/export even when review recommends do_not_build.")
    build_list.add_argument("--loader-version")
    build_list.add_argument("--memory-mb", type=int)
    _add_source_build_args(build_list)
    _add_prism_config_args(build_list)

    agent_pack = subcommands.add_parser("agent-pack", help="Verify, resolve, build/export, and report from a selected list.")
    agent_pack.add_argument("selected_mods")
    agent_pack.add_argument("--output", "--output-dir", dest="output_dir")
    agent_pack.add_argument("--dry-run", action="store_true")
    agent_pack.add_argument("--validate-launch", action="store_true")
    agent_pack.add_argument("--force", action="store_true", help="Allow build/export even when review recommends do_not_build.")
    agent_pack.add_argument("--loader-version")
    _add_source_build_args(agent_pack)
    _add_prism_config_args(agent_pack)

    autopilot = subcommands.add_parser("autopilot", help="Run autonomous build, private runtime validation, and safe repair loop.")
    autopilot.add_argument("selected_mods")
    autopilot.add_argument("--sources", default="modrinth,curseforge")
    autopilot.add_argument("--target-export", default="local_instance", choices=["local_instance", "prism_instance"])
    autopilot.add_argument("--minecraft-version", default="auto")
    autopilot.add_argument("--loader", default="auto")
    autopilot.add_argument("--loader-version")
    autopilot.add_argument("--candidate-versions")
    autopilot.add_argument("--candidate-loaders")
    autopilot.add_argument("--max-attempts", type=int, default=5)
    autopilot.add_argument("--memory-mb", type=int, default=4096)
    autopilot.add_argument("--timeout-seconds", type=int, default=180)
    autopilot.add_argument("--output-root")
    autopilot.add_argument("--run-id")
    autopilot.add_argument("--resume-run-id")
    autopilot.add_argument("--java-path")
    autopilot.add_argument("--inject-smoke-test", action=argparse.BooleanOptionalAction, default=True)
    autopilot.add_argument("--smoke-test-helper-path")
    autopilot.add_argument("--require-smoke-test-proof", action=argparse.BooleanOptionalAction, default=True)
    autopilot.add_argument("--minimum-stability-seconds", type=int, default=60)
    autopilot.add_argument("--allow-target-switch", action=argparse.BooleanOptionalAction, default=True)
    autopilot.add_argument("--allow-loader-switch", action=argparse.BooleanOptionalAction, default=True)
    autopilot.add_argument("--allow-minecraft-version-switch", action=argparse.BooleanOptionalAction, default=True)
    autopilot.add_argument("--allow-remove-content-mods", action="store_true")
    autopilot.add_argument("--allow-manual-sources", action="store_true")
    autopilot.add_argument("--keep-failed-instances", action="store_true")
    autopilot.add_argument("--json", action="store_true")

    validate_pack = subcommands.add_parser("validate-pack", help="Validate a generated pack directory through Prism when configured.")
    validate_pack.add_argument("pack_dir")
    validate_pack.add_argument("--pack-name")
    validate_pack.add_argument("--instance-id")
    validate_pack.add_argument("--check-config-only", action="store_true")
    _add_prism_config_args(validate_pack)

    repair_plan = subcommands.add_parser("repair-plan", help="Create repair options from a failed generation report.")
    repair_plan.add_argument("pack_dir", nargs="?")
    repair_plan.add_argument("--report", dest="report_path")

    apply_repair = subcommands.add_parser("apply-repair", help="Apply one selected repair option to a copy of selected_mods.json.")
    apply_repair.add_argument("repair_report")
    apply_repair.add_argument("--option-id", required=True)
    apply_repair.add_argument("--selected-mods", required=True)
    apply_repair.add_argument("--output", required=True)

    repair_pack = subcommands.add_parser("repair-pack", help="Build, validate, and stop at repair planning when validation fails.")
    repair_pack.add_argument("selected_mods")
    repair_pack.add_argument("--output", "--output-dir", dest="output_dir", required=True)
    repair_pack.add_argument("--dry-run", action="store_true")
    repair_pack.add_argument("--validate-launch", action="store_true")
    repair_pack.add_argument("--force", action="store_true", help="Allow build/export even when review recommends do_not_build.")
    _add_prism_config_args(repair_pack)

    generate = subcommands.add_parser("generate", help="Generate a modpack end-to-end.")
    generate.add_argument("prompt", nargs="*", help="Natural-language modpack prompt.")
    generate.add_argument("--profile", help="Path to a RequirementProfile JSON file.")
    generate.add_argument("--output-dir", help="Output directory. Defaults to output/generated/<pack>.")
    generate.add_argument("--dry-run", action="store_true", help="Build reports and .mrpack without downloading jars.")
    generate.add_argument("--limit", type=int, default=20, help="Modrinth results per search.")
    generate.add_argument("--max-mods", type=int, default=45, help="Maximum selected mods before dependencies.")

    analyze = subcommands.add_parser("analyze-failure", help="Classify a crash log.")
    analyze.add_argument("log_file")

    analyze_crash = subcommands.add_parser("analyze-crash", help="Analyze a Minecraft runtime crash report.")
    analyze_crash.add_argument("crash_report")
    analyze_crash.add_argument("--against", dest="selected_mods")
    analyze_crash.add_argument("--output", "--output-dir", dest="output_dir")

    stabilize = subcommands.add_parser("stabilize-pack", help="Verify, dry-run, launch-check, and repair runtime crashes.")
    stabilize.add_argument("selected_mods")
    stabilize.add_argument("--against", dest="pack_design")
    stabilize.add_argument("--output", "--output-dir", dest="output_dir")
    stabilize.add_argument("--max-attempts", type=int, default=3)
    stabilize.add_argument("--manual-crash-report")
    stabilize.add_argument("--no-launch", action="store_true")
    stabilize.add_argument("--prefer-remove-risky-optionals", action=argparse.BooleanOptionalAction, default=True)

    setup_launcher = subcommands.add_parser("setup-launcher", help="Create/import or validate a launcher instance.")
    setup_launcher.add_argument("pack_artifact")
    setup_launcher.add_argument("--launcher", default="auto")
    setup_launcher.add_argument("--instance-name", required=True)
    setup_launcher.add_argument("--minecraft-version", required=True)
    setup_launcher.add_argument("--loader", default="fabric")
    setup_launcher.add_argument("--loader-version")
    setup_launcher.add_argument("--memory-mb", type=int, default=8192)
    setup_launcher.add_argument("--output", "--output-dir", dest="output_dir")
    setup_launcher.add_argument("--validate-only", action="store_true")
    setup_launcher.add_argument("--instance-path")

    launch_check = subcommands.add_parser("launch-check", help="Validate launch/world-join readiness; dry-run is not playable proof.")
    launch_check.add_argument("selected_mods", nargs="?")
    launch_check.add_argument("--launcher", default="auto")
    launch_check.add_argument("--instance-path")
    launch_check.add_argument("--pack-dir")
    launch_check.add_argument("--wait-seconds", type=int, default=120)
    launch_check.add_argument("--manual", action="store_true")
    launch_check.add_argument("--crash-report")
    launch_check.add_argument("--latest-log")
    launch_check.add_argument("--inject-smoke-test-mod", action=argparse.BooleanOptionalAction, default=False)
    launch_check.add_argument("--validation-world", action="store_true")
    launch_check.add_argument("--keep-validation-world", action="store_true")
    launch_check.add_argument("--output", "--output-dir", dest="output_dir")
    _add_prism_config_args(launch_check)

    autonomous = subcommands.add_parser("autonomous-build", help="Run concept-to-Prism workflow; stable requires smoke-test runtime proof.")
    autonomous.add_argument("concept")
    autonomous.add_argument("--launcher", default="prism")
    autonomous.add_argument("--loader-version")
    autonomous.add_argument("--memory-mb", type=int, default=8192)
    autonomous.add_argument("--max-attempts", type=int, default=3)
    autonomous.add_argument("--wait-seconds", type=int, default=120)
    autonomous.add_argument("--output", "--output-dir", dest="output_dir")
    autonomous.add_argument("--no-launch", action="store_true")
    autonomous.add_argument("--manual-crash-report")
    autonomous.add_argument("--selected-mods")
    autonomous.add_argument("--sources", default="modrinth")
    autonomous.add_argument("--allow-manual-sources", action="store_true")
    autonomous.add_argument("--target-export", default="local_instance", choices=["modrinth_pack", "curseforge_manifest", "local_instance", "prism_instance"])
    autonomous.add_argument("--inject-smoke-test-mod", action=argparse.BooleanOptionalAction, default=True)
    autonomous.add_argument("--validation-world", action=argparse.BooleanOptionalAction, default=True)
    autonomous.add_argument("--keep-validation-world", action="store_true")
    _add_prism_config_args(autonomous)

    hud = subcommands.add_parser(
        "hud",
        help="Open the user-friendly terminal HUD / wizard.",
        description="Open the user-friendly terminal HUD / wizard.",
    )
    hud.add_argument("--overview", action="store_true", help="Print the main HUD menu and exit.")

    handoff = subcommands.add_parser("handoff", help="Cloud AI handoff helpers.")
    handoff_subcommands = handoff.add_subparsers(dest="handoff_command", required=True)
    handoff_export = handoff_subcommands.add_parser("export", help="Export a cloud AI handoff bundle.")
    handoff_export.add_argument("--concept", default="Minecraft modpack idea")
    handoff_export.add_argument("--output", required=True)
    handoff_validate = handoff_subcommands.add_parser("validate", help="Validate selected_mods.json format.")
    handoff_validate.add_argument("selected_mods")
    handoff_import = handoff_subcommands.add_parser("import", help="Import a selected_mods.json after validation.")
    handoff_import.add_argument("selected_mods")
    handoff_import.add_argument("--output", required=True)

    subcommands.add_parser("serve", help="Run FastAPI with uvicorn.")
    subcommands.add_parser("tui", help="Open terminal UI.")

    args = parser.parse_args(argv)
    if args.command == "start":
        if not args.idea:
            print(START_MESSAGE)
            return 0
        idea = " ".join(args.idea)
        artifact = write_agent_session(idea, Path(args.output_dir))
        _print_json(artifact)
        return 0

    if args.command == "tools":
        facade = AgentToolFacade(get_settings())
        _print_json(facade.list_tools())
        return 0
    if args.command == "search":
        facade = AgentToolFacade(get_settings())
        _print_json(
            asyncio.run(
                facade.search_mods(
                    args.query,
                    minecraft_version=args.minecraft_version,
                    loader=args.loader,
                    limit=args.limit,
                    include=args.include,
                    exclude=args.exclude,
                    capability=args.capability,
                    role=args.role,
                    client=args.client,
                    server=args.server,
                    min_downloads=args.min_downloads,
                    sort=args.sort,
                )
            )
        )
        return 0
    if args.command == "inspect":
        facade = AgentToolFacade(get_settings())
        _print_json(asyncio.run(facade.inspect_mod(args.identifier, minecraft_version=args.minecraft_version, loader=args.loader)))
        return 0
    if args.command == "compare":
        facade = AgentToolFacade(get_settings())
        _print_json(asyncio.run(facade.compare_mods(args.identifiers, minecraft_version=args.minecraft_version, loader=args.loader)))
        return 0
    if args.command == "review-list":
        facade = AgentToolFacade(get_settings())
        selected = _read_selected_mod_list(Path(args.selected_mods))
        pack_design = _read_pack_design(Path(args.pack_design)) if args.pack_design else None
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else Path("output") / "generated" / f"{safe_slug(selected.name, fallback='selected-mods')}-review"
        )
        _print_json(
            asyncio.run(
                facade.review_mod_list(
                    selected,
                    output_dir,
                    write_prompt=not args.no_prompt,
                    pack_design=pack_design,
                    pack_design_path=Path(args.pack_design) if args.pack_design else None,
                )
            )
        )
        return 0
    if args.command == "source-search":
        facade = AgentToolFacade(get_settings())
        _print_json(
            asyncio.run(
                facade.source_search(
                    args.query,
                    minecraft_version=args.minecraft_version,
                    loader=args.loader,
                    sources=_split_csv(args.sources),
                    limit=args.limit,
                    output_dir=Path(args.output_dir) if args.output_dir else None,
                )
            )
        )
        return 0
    if args.command == "source-inspect":
        facade = AgentToolFacade(get_settings())
        _print_json(
            asyncio.run(
                facade.source_inspect(
                    args.source_ref,
                    minecraft_version=args.minecraft_version,
                    loader=args.loader,
                    output_dir=Path(args.output_dir) if args.output_dir else None,
                )
            )
        )
        return 0
    if args.command == "source-resolve":
        facade = AgentToolFacade(get_settings())
        selected = _read_selected_mod_list(Path(args.selected_mods))
        if args.minecraft_version:
            selected.minecraft_version = args.minecraft_version
        if args.loader:
            selected.loader = args.loader
        _print_json(
            asyncio.run(
                facade.source_resolve(
                    selected,
                    sources=_split_csv(args.sources),
                    target_export=args.target_export,
                    autonomous=not args.allow_manual_sources,
                    allow_manual_sources=args.allow_manual_sources,
                    output_dir=Path(args.output_dir) if args.output_dir else None,
                )
            )
        )
        return 0
    if args.command == "agent-check":
        facade = AgentToolFacade(get_settings())
        selected = _read_selected_mod_list(Path(args.selected_mods))
        pack_design = _read_pack_design(Path(args.pack_design)) if args.pack_design else None
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else Path("output") / "generated" / f"{safe_slug(selected.name, fallback='selected-mods')}-agent-check"
        )
        _print_json(
            asyncio.run(
                facade.agent_check(
                    selected,
                    output_dir,
                    write_prompt=not args.no_prompt,
                    pack_design=pack_design,
                    pack_design_path=Path(args.pack_design) if args.pack_design else None,
                )
            )
        )
        return 0
    if args.command == "agent-workflow-prompt":
        concept_path = Path(args.concept)
        concept_text = concept_path.read_text(encoding="utf-8")
        workflow_name = args.name or _concept_title(concept_path, concept_text)
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else Path("output") / "generated" / f"{safe_slug(workflow_name, fallback='agent-workflow')}-agent-workflow"
        )
        _print_json(write_agent_workflow_prompt(concept_path, concept_text, output_dir=output_dir))
        return 0
    if args.command == "design-pack":
        facade = AgentToolFacade(get_settings())
        concept_path = Path(args.concept)
        concept_text = concept_path.read_text(encoding="utf-8")
        output_dir = Path(args.output_dir) if args.output_dir else Path("output") / "generated" / f"{safe_slug(args.name or concept_path.stem, fallback='pack-design')}-design"
        _print_json(
            facade.design_pack(
                concept_text,
                output_dir=output_dir,
                name=args.name,
                minecraft_version=args.minecraft_version,
                loader=args.loader,
            )
        )
        return 0
    if args.command == "review-design":
        facade = AgentToolFacade(get_settings())
        design_path = Path(args.pack_design)
        design = _read_pack_design(design_path)
        output_dir = Path(args.output_dir) if args.output_dir else design_path.parent
        _print_json(facade.review_pack_design(design, output_dir=output_dir, write_prompt=not args.no_prompt))
        return 0
    if args.command == "blueprint-pack":
        facade = AgentToolFacade(get_settings())
        design_path = Path(args.pack_design)
        design = _read_pack_design(design_path)
        output_dir = Path(args.output_dir) if args.output_dir else design_path.parent
        _print_json(
            facade.blueprint_pack(
                design,
                design_path=design_path,
                output_dir=output_dir,
                write_prompt=not args.no_prompt,
            )
        )
        return 0
    if args.command in {"verify-list", "resolve", "build-from-list", "agent-pack"}:
        facade = AgentToolFacade(_settings_for_args(args, force_validation=getattr(args, "validate_launch", False)))
        selected = _read_selected_mod_list(Path(args.selected_mods))
        if getattr(args, "minecraft_version", None):
            selected.minecraft_version = args.minecraft_version
        if getattr(args, "loader", None):
            selected.loader = args.loader
        if args.command == "verify-list":
            _print_json(asyncio.run(facade.verify_mod_list(selected)))
        elif args.command == "resolve":
            _print_json(asyncio.run(facade.resolve_mod_list(selected)))
        elif args.command == "build-from-list":
            output_dir = Path(args.output_dir or Path("output") / "generated" / selected.name.lower().replace(" ", "-"))
            _print_json(
                asyncio.run(
                    facade.build_from_list(
                        selected,
                        output_dir,
                        download=not args.dry_run,
                        validate_launch=args.validate_launch,
                        force=args.force,
                        loader_version=args.loader_version,
                        memory_mb=args.memory_mb,
                        sources=_split_csv(args.sources) if getattr(args, "sources", None) else None,
                        target_export=getattr(args, "target_export", None),
                        auto_target=getattr(args, "auto_target", False),
                        candidate_versions=_split_csv(args.candidate_versions) if getattr(args, "candidate_versions", None) else None,
                        candidate_loaders=_split_csv(args.candidate_loaders) if getattr(args, "candidate_loaders", None) else None,
                        allow_manual_sources=getattr(args, "allow_manual_sources", False),
                    )
                )
            )
        else:
            output_dir = Path(args.output_dir) if args.output_dir else None
            _print_json(
                asyncio.run(
                    facade.agent_service().agent_pack(
                        selected,
                        output_dir,
                        download=not args.dry_run,
                        validate_launch=args.validate_launch,
                        force=args.force,
                        sources=_split_csv(args.sources) if getattr(args, "sources", None) else None,
                        target_export=getattr(args, "target_export", None),
                        auto_target=getattr(args, "auto_target", False),
                        candidate_versions=_split_csv(args.candidate_versions) if getattr(args, "candidate_versions", None) else None,
                        candidate_loaders=_split_csv(args.candidate_loaders) if getattr(args, "candidate_loaders", None) else None,
                        allow_manual_sources=getattr(args, "allow_manual_sources", False),
                        loader_version=getattr(args, "loader_version", None),
                    )
                )
            )
        return 0
    if args.command == "autopilot":
        try:
            autopilot_report = asyncio.run(
                run_autopilot(
                    AutopilotRequest(
                        selected_mods_path=args.selected_mods,
                        sources=_split_csv(args.sources),
                        run_id=args.run_id,
                        resume_run_id=args.resume_run_id,
                        target_export=args.target_export,
                        minecraft_version=args.minecraft_version,
                        loader=args.loader,
                        loader_version=args.loader_version,
                        candidate_versions=_split_csv(args.candidate_versions),
                        candidate_loaders=_split_csv(args.candidate_loaders),
                        max_attempts=args.max_attempts,
                        memory_mb=args.memory_mb,
                        timeout_seconds=args.timeout_seconds,
                        output_root=args.output_root,
                        java_path=args.java_path,
                        allow_manual_sources=args.allow_manual_sources,
                        allow_target_switch=args.allow_target_switch,
                        allow_loader_switch=args.allow_loader_switch,
                        allow_minecraft_version_switch=args.allow_minecraft_version_switch,
                        allow_remove_content_mods=args.allow_remove_content_mods,
                        keep_failed_instances=args.keep_failed_instances,
                        inject_smoke_test=args.inject_smoke_test,
                        smoke_test_helper_path=args.smoke_test_helper_path,
                        require_smoke_test_proof=args.require_smoke_test_proof,
                        minimum_stability_seconds=args.minimum_stability_seconds,
                    )
                )
            )
        except (OSError, ValueError) as exc:
            autopilot_report = AutopilotReport(
                status="failed",
                final_minecraft_version=args.minecraft_version,
                final_loader=args.loader,
                final_loader_version=args.loader_version,
                attempts=[],
                final_instance_path=None,
                final_export_path=None,
                summary=f"Invalid Autopilot request: {exc}",
                warnings=[],
                blockers=[
                    AutopilotBlocker(
                        kind="invalid_request",
                        message=str(exc),
                        severity="fatal",
                        agent_can_retry=True,
                        user_action_required=True,
                        suggested_next_step="Fix the selected_mods.json path or request values and run Autopilot again.",
                    )
                ],
            )
        code = exit_code_for_autopilot_report(autopilot_report)
        if args.json:
            _print_json(autopilot_report)
        else:
            _print_autopilot_human(autopilot_report)
        return code
    if args.command == "validate-pack":
        facade = AgentToolFacade(_settings_for_args(args, force_validation=True))
        _print_json(
            asyncio.run(
                facade.validate_pack(
                    Path(args.pack_dir),
                    pack_name=args.pack_name,
                    instance_id=args.instance_id,
                    check_config_only=args.check_config_only,
                )
            )
        )
        return 0
    if args.command == "repair-plan":
        facade = AgentToolFacade(get_settings())
        _print_json(
            asyncio.run(
                facade.create_repair_plan(
                    Path(args.pack_dir) if args.pack_dir else None,
                    report_path=Path(args.report_path) if args.report_path else None,
                )
            )
        )
        return 0
    if args.command == "apply-repair":
        facade = AgentToolFacade(get_settings())
        _print_json(
            asyncio.run(
                facade.apply_repair_option(
                    Path(args.repair_report),
                    option_id=args.option_id,
                    selected_mods_path=Path(args.selected_mods),
                    output_path=Path(args.output),
                )
            )
        )
        return 0
    if args.command == "repair-pack":
        facade = AgentToolFacade(_settings_for_args(args, force_validation=getattr(args, "validate_launch", False)))
        selected = _read_selected_mod_list(Path(args.selected_mods))
        output_dir = Path(args.output_dir)
        build = asyncio.run(
            facade.build_from_list(
                selected,
                output_dir,
                download=not args.dry_run,
                validate_launch=args.validate_launch,
                force=args.force,
            )
        )
        if build.validation_status in {"failed", "timeout"} or build.crash_analysis:
            _print_json(asyncio.run(facade.create_repair_plan(output_dir)))
        else:
            _print_json(build)
        return 0
    if args.command == "generate":
        if not args.profile and not args.prompt:
            parser.error("generate requires: provide a prompt or --profile")
        facade = AgentToolFacade(get_settings())
        profile = None
        if args.profile:
            profile = RequirementProfile.model_validate_json(
                Path(args.profile).read_text(encoding="utf-8")
            )
        prompt = " ".join(args.prompt) if args.prompt else None
        report = asyncio.run(
            facade.generate_modpack(
                GenerationRequest(
                    prompt=prompt,
                    profile=profile,
                    output_dir=args.output_dir,
                    dry_run=args.dry_run,
                    limit=args.limit,
                    max_mods=args.max_mods,
                )
            )
        )
        _print_json(report)
        return 0
    if args.command == "analyze-failure":
        facade = AgentToolFacade(get_settings())
        _print_json(facade.analyze_failure(Path(args.log_file).read_text(encoding="utf-8")))
        return 0
    if args.command == "analyze-crash":
        facade = AgentToolFacade(get_settings())
        crash_path = Path(args.crash_report)
        selected = _read_selected_mod_list(Path(args.selected_mods)) if args.selected_mods else None
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else crash_path.parent
        )
        _print_json(
            asyncio.run(
                facade.analyze_crash(
                    crash_path.read_text(encoding="utf-8", errors="replace"),
                    selected=selected,
                    selected_mods_path=str(Path(args.selected_mods)) if args.selected_mods else None,
                    crash_report_path=str(crash_path),
                    output_dir=output_dir,
                )
            )
        )
        return 0
    if args.command == "setup-launcher":
        facade = AgentToolFacade(_settings_for_args(args))
        output_dir = Path(args.output_dir) if args.output_dir else Path(args.pack_artifact).parent
        instance, validation = asyncio.run(
            facade.setup_launcher(
                Path(args.pack_artifact),
                output_dir,
                launcher=args.launcher,
                instance_name=args.instance_name,
                minecraft_version=args.minecraft_version,
                loader=args.loader,
                loader_version=args.loader_version,
                memory_mb=args.memory_mb,
                validate_only=args.validate_only,
                instance_path=Path(args.instance_path) if args.instance_path else None,
            )
        )
        _print_json({"instance": instance, "validation": validation})
        return 0
    if args.command == "launch-check":
        facade = AgentToolFacade(_settings_for_args(args, force_validation=bool(args.instance_path)))
        selected = _read_selected_mod_list(Path(args.selected_mods)) if args.selected_mods else None
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else Path(args.pack_dir or args.instance_path or "output/generated/launch-check")
        )
        if args.instance_path or not args.selected_mods:
            _print_json(
                asyncio.run(
                    facade.launcher_launch_check(
                        launcher=args.launcher,
                        instance_path=Path(args.instance_path) if args.instance_path else None,
                        wait_seconds=args.wait_seconds,
                        output_dir=output_dir,
                        selected=selected,
                        crash_report=Path(args.crash_report) if args.crash_report else None,
                        latest_log=Path(args.latest_log) if args.latest_log else None,
                        inject_smoke_test=args.inject_smoke_test_mod,
                        validation_world=args.validation_world,
                        keep_validation_world=args.keep_validation_world,
                    )
                )
            )
        else:
            _print_json(
                asyncio.run(
                    facade.launch_check(
                        selected,
                        Path(args.pack_dir),
                        manual=args.manual,
                        crash_report=Path(args.crash_report) if args.crash_report else None,
                    )
                )
            )
        return 0
    if args.command == "autonomous-build":
        facade = AgentToolFacade(_settings_for_args(args, force_validation=not args.no_launch))
        concept_path = Path(args.concept)
        selected = _read_selected_mod_list(Path(args.selected_mods)) if args.selected_mods else None
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else Path("output") / "generated" / f"{safe_slug(_concept_title(concept_path, concept_path.read_text(encoding='utf-8', errors='replace')), fallback='autonomous-pack')}-autonomous"
        )
        _print_json(
            asyncio.run(
                facade.autonomous_build(
                    concept_path,
                    output_dir,
                    selected=selected,
                    launcher=args.launcher,
                    loader_version=args.loader_version,
                    memory_mb=args.memory_mb,
                    max_attempts=args.max_attempts,
                    wait_seconds=args.wait_seconds,
                    no_launch=args.no_launch,
                    manual_crash_report=Path(args.manual_crash_report) if args.manual_crash_report else None,
                    sources=_split_csv(args.sources),
                    allow_manual_sources=args.allow_manual_sources,
                    target_export=args.target_export,
                    inject_smoke_test_mod=args.inject_smoke_test_mod,
                    validation_world=args.validation_world,
                    keep_validation_world=args.keep_validation_world,
                )
            )
        )
        return 0
    if args.command == "stabilize-pack":
        facade = AgentToolFacade(get_settings())
        selected = _read_selected_mod_list(Path(args.selected_mods))
        pack_design = _read_pack_design(Path(args.pack_design)) if args.pack_design else None
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else Path("output") / "generated" / f"{safe_slug(selected.name, fallback='selected-mods')}-stabilized"
        )
        _print_json(
            asyncio.run(
                facade.stabilize_pack(
                    selected,
                    output_dir,
                    pack_design=pack_design,
                    pack_design_path=Path(args.pack_design) if args.pack_design else None,
                    max_attempts=args.max_attempts,
                    manual_crash_report=Path(args.manual_crash_report) if args.manual_crash_report else None,
                    no_launch=args.no_launch,
                    prefer_remove_risky_optionals=args.prefer_remove_risky_optionals,
                )
            )
        )
        return 0
    if args.command == "hud":
        from mythweaver.cli.hud import render_hud_overview, run_hud

        if args.overview:
            print(render_hud_overview())
        else:
            run_hud()
        return 0
    if args.command == "handoff":
        if args.handoff_command == "export":
            _print_json(export_cloud_handoff_zip(concept=args.concept, output_zip=Path(args.output)))
        elif args.handoff_command == "validate":
            _print_json(validate_selected_mods_file(Path(args.selected_mods)))
        elif args.handoff_command == "import":
            _print_json(import_selected_mods_file(Path(args.selected_mods), output=Path(args.output)))
        return 0
    if args.command == "serve":
        try:
            import uvicorn
        except ImportError as exc:
            raise RuntimeError("uvicorn is not installed. Run `pip install -e .` first.") from exc
        uvicorn.run(create_app(get_settings()), host="127.0.0.1", port=8765)
        return 0
    if args.command == "tui":
        from mythweaver.cli.tui import run_tui

        run_tui()
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


def main(argv: list[str] | None = None) -> int:
    return _fallback_main(argv)


def _read_selected_mod_list(path: Path) -> SelectedModList:
    return SelectedModList.model_validate_json(path.read_text(encoding="utf-8"))


def _read_pack_design(path: Path) -> PackDesign:
    return PackDesign.model_validate_json(path.read_text(encoding="utf-8"))


def _concept_title(path: Path, concept_text: str) -> str:
    for line in concept_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return path.stem or "agent-workflow"


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
