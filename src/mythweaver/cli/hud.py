from __future__ import annotations

import asyncio
from pathlib import Path

from mythweaver.core.settings import get_settings
from mythweaver.handoff import create_cloud_handoff_bundle, validate_selected_mods_file, write_cloud_ai_fix_selected_mods_prompt
from mythweaver.schemas.contracts import SelectedModList
from mythweaver.tools.facade import AgentToolFacade


def render_hud_overview() -> str:
    return "\n".join(
        [
            "MythWeaver Terminal HUD",
            "",
            "1. Build a pack from a selected_mods.json",
            "2. I need ChatGPT/Claude/Gemini to make me a selected_mods.json",
            "3. Validate or repair an existing generated pack",
            "4. Search/inspect mods manually",
            "5. Settings / Prism validation setup",
            "6. Exit",
            "",
            "Exact commands:",
            "python -m mythweaver.cli.main handoff export --concept \"your pack idea\" --output mythweaver_handoff.zip",
            "python -m mythweaver.cli.main handoff validate selected_mods.json",
            "python -m mythweaver.cli.main verify-list selected_mods.json",
            "python -m mythweaver.cli.main build-from-list selected_mods.json --output output/generated/<pack-name>",
            "python -m mythweaver.cli.main repair-plan output/generated/<pack-name>",
        ]
    )


def run_hud() -> None:
    print(render_hud_overview())
    while True:
        choice = input("\nChoose an option: ").strip()
        if choice == "1":
            _flow_build_from_json()
        elif choice == "2":
            _flow_cloud_handoff()
        elif choice == "3":
            _flow_validate_or_repair()
        elif choice == "4":
            _flow_manual_search()
        elif choice == "5":
            _flow_settings()
        elif choice == "6" or choice.lower() in {"q", "quit", "exit"}:
            print("Good luck with the pack. MythWeaver will be here when you are ready.")
            return
        else:
            print("Please choose 1-6.")


def _flow_build_from_json() -> None:
    path = Path(input("Path to selected_mods.json: ").strip().strip('"'))
    validation = validate_selected_mods_file(path, output_dir=Path("output") / "generated" / "hud")
    if not validation["valid"]:
        print("That JSON file is not in the format MythWeaver expects.")
        print(f"Fix prompt saved: {validation['cloud_ai_fix_prompt']}")
        print(f"Command: python -m mythweaver.cli.main handoff validate {path}")
        return
    selected = validation["selected_mods"]
    facade = AgentToolFacade(get_settings())
    verify = asyncio.run(facade.verify_mod_list(selected))
    if verify.status == "failed":
        output_dir = Path("output") / "generated" / _slug(selected.name)
        prompt = write_cloud_ai_fix_selected_mods_prompt(path, output_dir=output_dir, verify_report=verify)
        print("Some selected mods need extra mods or have incompatible requirements.")
        print(f"Cloud AI fix prompt saved: {prompt}")
        print(f"Command: python -m mythweaver.cli.main verify-list {path}")
        return
    print("The selected mod list passed Modrinth verification.")
    print(f"Command: python -m mythweaver.cli.main build-from-list {path} --output output/generated/{_slug(selected.name)}")
    if input("Build now? [y/N]: ").strip().lower() == "y":
        output_dir = Path("output") / "generated" / _slug(selected.name)
        report = asyncio.run(facade.build_from_list(selected, output_dir))
        print(f"Build report saved in: {output_dir}")
        print(f"Status: {report.status}")
        if input("Run launch validation through Prism now? [y/N]: ").strip().lower() == "y":
            validation = asyncio.run(facade.validate_pack(output_dir, pack_name=selected.name, force_validation=True))
            print(f"Launch validation status: {validation.status}")
            print(validation.details or validation.raw_summary or "")
            if validation.status in {"failed", "timeout"} and input("Create a repair plan? [y/N]: ").strip().lower() == "y":
                repair = asyncio.run(facade.create_repair_plan(output_dir))
                print(f"Repair report saved: {output_dir / 'repair_report.md'}")
                print(f"Repair options: {len(repair.repair_options)}")


def _flow_cloud_handoff() -> None:
    concept = input("Describe your modpack idea: ").strip()
    minecraft_version = input("Minecraft version [1.20.1]: ").strip() or "1.20.1"
    loader = "fabric"
    size = input("Approx size: small, medium, or large [medium]: ").strip() or "medium"
    performance = input("Performance priority: high, balanced, visuals first [balanced]: ").strip() or "balanced"
    shaders = input("Shaders: yes, no, recommendations only [recommendations only]: ").strip() or "recommendations only"
    avoid = input("Things to avoid, comma-separated [none]: ").strip()
    output = Path("output") / "handoff" / _slug(concept)
    result = create_cloud_handoff_bundle(
        concept=concept,
        output_dir=output,
        minecraft_version=minecraft_version,
        loader=loader,
        size=size,
        performance_priority=performance,
        shaders=shaders,
        avoid_terms=avoid,
    )
    print(f"Handoff files saved: {result['output_dir']}")
    print("Upload or paste cloud_ai_request.md into ChatGPT/Claude/Gemini.")
    print("Ask it to return selected_mods.json, then come back and choose option 1.")


def _flow_validate_or_repair() -> None:
    pack_dir = Path(input("Generated pack output folder: ").strip().strip('"'))
    print("1. Check Prism config only")
    print("2. Run validate-pack")
    print("3. Run repair-plan")
    print("4. Apply repair option")
    choice = input("Choose: ").strip()
    facade = AgentToolFacade(get_settings())
    if choice == "1":
        report = asyncio.run(facade.validate_pack(pack_dir, force_validation=False, check_config_only=True))
        print(f"Validation status: {report.status}")
        print(report.details)
    elif choice == "2":
        print(f"Command: python -m mythweaver.cli.main validate-pack {pack_dir}")
        report = asyncio.run(facade.validate_pack(pack_dir))
        print(f"Validation status: {report.status}")
    elif choice == "3":
        print(f"Command: python -m mythweaver.cli.main repair-plan {pack_dir}")
        repair = asyncio.run(facade.create_repair_plan(pack_dir))
        print(f"Repair report saved: {pack_dir / 'repair_report.md'}")
        for option in repair.repair_options:
            print(f"{option.id}: {option.action_type} {option.target_slug or ''} ({option.risk_level})")
    elif choice == "4":
        repair_report = Path(input("Path to repair_report.json: ").strip().strip('"'))
        option_id = input("Option ID to apply: ").strip()
        selected = Path(input("Original selected_mods.json: ").strip().strip('"'))
        output = Path(input("Output repaired JSON path: ").strip().strip('"'))
        result = asyncio.run(
            facade.apply_repair_option(repair_report, option_id=option_id, selected_mods_path=selected, output_path=output)
        )
        print(f"Repaired selected mods written: {result['output_path']}")


def _flow_manual_search() -> None:
    facade = AgentToolFacade(get_settings())
    print("1. Search Modrinth")
    print("2. Inspect a mod")
    print("3. Compare mods")
    print("4. Verify selected list")
    choice = input("Choose: ").strip()
    if choice == "1":
        query = input("Search query: ").strip()
        print(f"Command: python -m mythweaver.cli.main search \"{query}\" --loader fabric --minecraft 1.20.1")
        print(asyncio.run(facade.search_mods(query, loader="fabric", minecraft_version="1.20.1")))
    elif choice == "2":
        identifier = input("Slug or Modrinth ID: ").strip()
        print(f"Command: python -m mythweaver.cli.main inspect {identifier} --loader fabric --minecraft 1.20.1")
        print(asyncio.run(facade.inspect_mod(identifier, loader="fabric", minecraft_version="1.20.1")))
    elif choice == "3":
        identifiers = input("Slugs/IDs separated by spaces: ").split()
        print(f"Command: python -m mythweaver.cli.main compare {' '.join(identifiers)} --loader fabric --minecraft 1.20.1")
        print(asyncio.run(facade.compare_mods(identifiers, loader="fabric", minecraft_version="1.20.1")))
    elif choice == "4":
        path = Path(input("Path to selected_mods.json: ").strip().strip('"'))
        selected = SelectedModList.model_validate_json(path.read_text(encoding="utf-8"))
        print(f"Command: python -m mythweaver.cli.main verify-list {path}")
        print(asyncio.run(facade.verify_mod_list(selected)))


def _flow_settings() -> None:
    settings = get_settings()
    print("Settings / Prism validation setup")
    print(f"Prism executable path: {settings.resolved_prism_path or 'not configured'}")
    print(f"Prism instances path: {settings.resolved_prism_root or 'not configured'}")
    print(f"Launch timeout seconds: {settings.launch_timeout_seconds}")
    print(f"Validation enabled: {settings.validation_enabled}")
    print("Prism is optional. You can build .mrpack files without it.")
    if input("Update Prism settings in .env? [y/N]: ").strip().lower() == "y":
        prism_path = input("Prism executable path: ").strip().strip('"')
        instances_path = input("Prism instances path: ").strip().strip('"')
        timeout = input("Launch timeout seconds [300]: ").strip() or "300"
        _update_env(
            {
                "MYTHWEAVER_PRISM_EXECUTABLE_PATH": prism_path,
                "MYTHWEAVER_PRISM_INSTANCES_PATH": instances_path,
                "MYTHWEAVER_LAUNCH_TIMEOUT_SECONDS": timeout,
                "MYTHWEAVER_VALIDATION_ENABLED": "true",
            }
        )
        print("Saved Prism settings to .env.")
    print("Exact config check command:")
    print("python -m mythweaver.cli.main validate-pack output/generated/<pack-name> --check-config-only --validation-enabled")


def _slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in value).strip("-") or "pack"


def _update_env(values: dict[str, str]) -> None:
    env_path = Path(".env")
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                existing[key.strip()] = value.strip()
    for key, value in values.items():
        if value:
            existing[key] = value
    env_path.write_text("\n".join(f"{key}={value}" for key, value in sorted(existing.items())) + "\n", encoding="utf-8")
