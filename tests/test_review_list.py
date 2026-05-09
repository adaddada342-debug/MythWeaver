import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.test_agent_selected_workflow import FakeAgentFacade, FakeAgentModrinth, project_payload
from tests.test_pipeline_discovery import version_payload


class ReviewModrinth(FakeAgentModrinth):
    def __init__(self):
        super().__init__()
        extra = {
            "xaeros-minimap": project_payload("xaero-mini-id", slug="xaeros-minimap", title="Xaero's Minimap", categories=["utility"]),
            "xaeros-world-map": project_payload("xaero-world-id", slug="xaeros-world-map", title="Xaero's World Map", categories=["utility"]),
            "journeymap": project_payload("journey-id", slug="journeymap", title="JourneyMap", categories=["utility"]),
            "terralith": project_payload("terralith-id", slug="terralith", title="Terralith", categories=["worldgen"]),
            "waystones": project_payload("waystones-id", slug="waystones", title="Waystones", categories=["utility"]),
            "avaritia": project_payload("avaritia-id", slug="avaritia", title="Avaritia Overpowered Gear", categories=["equipment"]),
            "from-the-fog": project_payload("fog-id", slug="from-the-fog", title="From The Fog Horror", categories=["adventure"]),
            "tough-as-nails": project_payload("tough-id", slug="tough-as-nails", title="Tough As Nails temperature thirst survival", categories=["adventure"]),
            "create": project_payload("create-id", slug="create", title="Create", categories=["technology"]),
            "botania": project_payload("botania-id", slug="botania", title="Botania Magic", categories=["magic"]),
            "ars-nouveau": project_payload("ars-id", slug="ars-nouveau", title="Ars Nouveau Magic Spells", categories=["magic"]),
            "visuality": project_payload("visuality-id", slug="visuality", title="Visuality", categories=["decoration"]),
            "farmers-delight": project_payload("farmers-id", slug="farmers-delight", title="Farmer's Delight cooking farming food", categories=["food"]),
            "farmers-delight-refabricated": project_payload("fdr-id", slug="farmers-delight-refabricated", title="Farmer's Delight Refabricated", categories=["food"]),
            "croptopia": project_payload("croptopia-id", slug="croptopia", title="Croptopia", categories=["food"]),
            "naturalist": project_payload("naturalist-id", slug="naturalist", title="Naturalist wildlife animals", categories=["mobs"]),
            "ct-overhaul-village": project_payload("ctov-id", slug="ct-overhaul-village", title="ChoiceTheorem's Overhauled Village", categories=["worldgen"]),
            "regions-unexplored": project_payload("regions-id", slug="regions-unexplored", title="Regions Unexplored", categories=["worldgen"]),
            "tectonic": project_payload("tectonic-id", slug="tectonic", title="Tectonic terrain", categories=["worldgen"]),
            "chipped": project_payload("chipped-id", slug="chipped", title="Chipped", categories=["decoration"]),
            "rechiseled": project_payload("rechiseled-id", slug="rechiseled", title="Rechiseled", categories=["decoration"]),
            "toms-storage": project_payload("toms-id", slug="toms-storage", title="Tom's Simple Storage", categories=["utility"]),
            "ambientsounds": project_payload("ambient-id", slug="ambientsounds", title="AmbientSounds", categories=["decoration"]),
            "travelersbackpack": project_payload("traveler-id", slug="travelersbackpack", title="Traveler's Backpack", categories=["storage"]),
            "simple-storage-network": project_payload("simple-storage-id", slug="simple-storage-network", title="Simple Storage Network", categories=["storage"]),
            "lava-chicken-disc": project_payload(
                "lava-disc-id",
                slug="lava-chicken-disc",
                title="Lava Chicken Disc",
                categories=["decoration"],
                versions=["1.20.1"],
            )
            | {"downloads": 50, "updated": "2020-01-01T00:00:00Z"},
        }
        self.projects.update(extra)
        self.projects.update({project["id"]: project for project in extra.values()})
        self.versions.update(
            {
                "xaeros-minimap": [version_payload("xaero-mini-id")],
                "xaero-mini-id": [version_payload("xaero-mini-id")],
                "xaeros-world-map": [version_payload("xaero-world-id")],
                "xaero-world-id": [version_payload("xaero-world-id")],
                "journeymap": [version_payload("journey-id")],
                "journey-id": [version_payload("journey-id")],
                "terralith": [version_payload("terralith-id")],
                "terralith-id": [version_payload("terralith-id")],
                "waystones": [version_payload("waystones-id")],
                "waystones-id": [version_payload("waystones-id")],
                "avaritia": [version_payload("avaritia-id")],
                "avaritia-id": [version_payload("avaritia-id")],
                "from-the-fog": [version_payload("fog-id")],
                "fog-id": [version_payload("fog-id")],
                "tough-as-nails": [version_payload("tough-id")],
                "tough-id": [version_payload("tough-id")],
                "create": [version_payload("create-id")],
                "create-id": [version_payload("create-id")],
                "botania": [version_payload("botania-id")],
                "botania-id": [version_payload("botania-id")],
                "ars-nouveau": [version_payload("ars-id")],
                "ars-id": [version_payload("ars-id")],
                "visuality": [version_payload("visuality-id")],
                "visuality-id": [version_payload("visuality-id")],
                "farmers-delight": [version_payload("farmers-id")],
                "farmers-id": [version_payload("farmers-id")],
                "farmers-delight-refabricated": [version_payload("fdr-id")],
                "fdr-id": [version_payload("fdr-id")],
                "croptopia": [version_payload("croptopia-id")],
                "croptopia-id": [version_payload("croptopia-id")],
                "naturalist": [version_payload("naturalist-id")],
                "naturalist-id": [version_payload("naturalist-id")],
                "ct-overhaul-village": [version_payload("ctov-id")],
                "ctov-id": [version_payload("ctov-id")],
                "regions-unexplored": [version_payload("regions-id")],
                "regions-id": [version_payload("regions-id")],
                "tectonic": [version_payload("tectonic-id")],
                "tectonic-id": [version_payload("tectonic-id")],
                "chipped": [version_payload("chipped-id")],
                "chipped-id": [version_payload("chipped-id")],
                "rechiseled": [version_payload("rechiseled-id")],
                "rechiseled-id": [version_payload("rechiseled-id")],
                "toms-storage": [version_payload("toms-id")],
                "toms-id": [version_payload("toms-id")],
                "ambientsounds": [version_payload("ambient-id")],
                "ambient-id": [version_payload("ambient-id")],
                "travelersbackpack": [version_payload("traveler-id")],
                "traveler-id": [version_payload("traveler-id")],
                "simple-storage-network": [version_payload("simple-storage-id")],
                "simple-storage-id": [version_payload("simple-storage-id")],
                "lava-chicken-disc": [version_payload("lava-disc-id") | {"date_published": "2020-01-01T00:00:00Z"}],
                "lava-disc-id": [version_payload("lava-disc-id") | {"date_published": "2020-01-01T00:00:00Z"}],
            }
        )
        for slug in [
            "modernfix",
            "immediatelyfast",
            "entityculling",
            "modmenu",
            "jade",
            "emi",
            "appleskin",
            "mouse-tweaks",
            "shulkerboxtooltip",
            "inventory-profiles-next",
            "supplementaries",
            "another-furniture",
            "handcrafted",
            "macaws-bridges",
            "macaws-doors",
            "macaws-windows",
            "macaws-roofs",
            "croptopia-delight",
            "explorify",
            "sound-physics-remastered",
        ]:
            if slug not in self.projects:
                project_id = f"{slug}-id"
                self.projects[slug] = project_payload(project_id, slug=slug, title=slug.replace("-", " ").title(), categories=["utility"])
                self.projects[project_id] = self.projects[slug]
                self.versions[slug] = [version_payload(project_id)]
                self.versions[project_id] = [version_payload(project_id)]


class ReviewFacade(FakeAgentFacade):
    def __init__(self, settings=None):
        super().__init__()
        self.modrinth = ReviewModrinth()
        if settings is not None:
            self.settings = settings


class ReviewSettings:
    def __init__(self, root: Path):
        self.data_dir = root / "data"
        self.output_dir = root / "output"
        self.cache_db = root / "cache.sqlite3"
        self.validation_enabled = False


class ReviewListTests(unittest.IsolatedAsyncioTestCase):
    def selected(self, mods, *, name="Review Pack", summary="Adventure pack with exploration."):
        from mythweaver.schemas.contracts import SelectedModList

        return SelectedModList.model_validate(
            {
                "name": name,
                "summary": summary,
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": mods,
            }
        )

    def test_cli_help_includes_review_list(self):
        from mythweaver.cli.main import _fallback_main

        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            _fallback_main(["review-list", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Review selected_mods.json quality", stdout.getvalue())
        self.assertIn("--against", stdout.getvalue())

    def test_cli_help_includes_agent_check(self):
        from mythweaver.cli.main import _fallback_main

        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            _fallback_main(["agent-check", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("AI-agent backend verification report", stdout.getvalue())
        self.assertIn("--against", stdout.getvalue())

    def test_cli_help_includes_agent_workflow_prompt(self):
        from mythweaver.cli.main import _fallback_main

        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            _fallback_main(["agent-workflow-prompt", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Cursor/Codex workflow prompt", stdout.getvalue())
        self.assertIn("--output-dir", stdout.getvalue())
        self.assertIn("--name", stdout.getvalue())

    def test_agent_workflow_prompt_writes_prompt_manifest_and_json_summary(self):
        from mythweaver.cli.main import _fallback_main

        root = Path.cwd() / "output" / "test-agent-workflow-prompt"
        concept = root / "concept.md"
        output_dir = root / "workflow"
        root.mkdir(parents=True, exist_ok=True)
        concept.write_text("# Cozy Beautiful World\n\nA peaceful farming and building pack.", encoding="utf-8")

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = _fallback_main(
                [
                    "agent-workflow-prompt",
                    str(concept),
                    "--output-dir",
                    str(output_dir),
                    "--name",
                    "Cozy Beautiful World",
                ]
            )

        self.assertEqual(exit_code, 0)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["name"], "Cozy Beautiful World")
        self.assertTrue(Path(summary["prompt_path"]).is_file())
        self.assertTrue(Path(summary["workflow_manifest_path"]).is_file())
        self.assertTrue((output_dir / "cursor_composer_prompt.md").is_file())
        self.assertTrue((output_dir / "workflow_manifest.json").is_file())

        prompt = (output_dir / "cursor_composer_prompt.md").read_text(encoding="utf-8")
        self.assertIn("You are the creative modpack designer", prompt)
        self.assertIn("MythWeaver is your backend", prompt)
        self.assertIn("design-pack", prompt)
        self.assertIn("blueprint-pack", prompt)
        self.assertIn("agent-check", prompt)
        self.assertIn("verify-list", prompt)
        self.assertIn("build-from-list <selected_mods.json> --dry-run", prompt)
        self.assertIn("Do not invent mods", prompt)
        self.assertIn("Do not silently drop mods", prompt)
        self.assertIn("Treat warnings and ai_judgment_needed as signals", prompt)

        manifest = json.loads((output_dir / "workflow_manifest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(manifest["recommended_steps"]), 10)
        self.assertEqual(manifest["recommended_steps"][0]["step_id"], "01_concept")
        self.assertTrue(any(step["command"] and "agent-check" in step["command"] for step in manifest["recommended_steps"]))

    def test_readme_mentions_ai_agent_backend(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("MythWeaver as an AI agent backend", readme)
        self.assertIn("agent-workflow-prompt concepts/cozy_beautiful_world.md", readme)

    async def test_valid_review_writes_report_and_prompt(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-review-valid"
        selected = self.selected(
            [
                {"slug": "sodium", "role": "foundation", "reason_selected": "Renderer optimization"},
                {"slug": "lithium", "role": "foundation", "reason_selected": "Logic optimization"},
                {"slug": "ferrite-core", "role": "foundation", "reason_selected": "Memory optimization"},
                {"slug": "terralith", "role": "theme", "reason_selected": "Worldgen"},
                {"slug": "when-dungeons-arise", "role": "theme", "reason_selected": "Structures and dungeons"},
                {"slug": "xaeros-minimap", "role": "utility", "reason_selected": "Navigation"},
            ]
        )

        report = await AgentModpackService(ReviewFacade(ReviewSettings(root))).review_mod_list(selected, root)

        self.assertIn(report.status, {"passed", "warnings"})
        self.assertGreaterEqual(report.score, 0)
        self.assertTrue(report.verdict)
        self.assertTrue((root / "review_report.json").is_file())
        self.assertTrue((root / "cloud_ai_review_prompt.md").is_file())

    async def test_agent_check_writes_report_and_prompt_for_ai_backend(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        root = Path.cwd() / "output" / "test-agent-check"
        report = await AgentModpackService(ReviewFacade(ReviewSettings(root))).agent_check(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "journeymap", "role": "utility", "reason_selected": "Map"},
                    {"slug": "xaeros-minimap", "role": "utility", "reason_selected": "Minimap"},
                ]
            ),
            root,
            pack_design=infer_pack_design_from_concept("cozy farming peaceful village cooking"),
            pack_design_path=Path("pack_design.json"),
        )

        self.assertTrue((root / "agent_check_report.json").is_file())
        self.assertTrue((root / "cloud_ai_agent_repair_prompt.md").is_file())
        self.assertEqual(report.build_permission, "allowed_with_warnings")
        self.assertFalse(report.hard_blockers)
        self.assertTrue(any(finding.kind == "possible_duplicate" for finding in report.ai_judgment_needed))
        prompt = (root / "cloud_ai_agent_repair_prompt.md").read_text(encoding="utf-8")
        self.assertIn("You are the creative modpack designer", prompt)
        self.assertIn("MythWeaver is the backend verification tool", prompt)
        self.assertIn("Do not blindly obey possible duplicate warnings", prompt)

    async def test_agent_check_blocks_unsupported_mod_and_keeps_subjective_separate(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        report = await AgentModpackService(ReviewFacade()).agent_check(
            self.selected(
                [
                    {"slug": "forge-only", "role": "theme", "reason_selected": "Unsupported"},
                    {"slug": "journeymap", "role": "utility", "reason_selected": "Map"},
                    {"slug": "xaeros-minimap", "role": "utility", "reason_selected": "Minimap"},
                ]
            )
        )

        self.assertEqual(report.build_permission, "blocked")
        self.assertTrue(any("forge-only" in finding.affected_mods for finding in report.hard_blockers))
        self.assertFalse(any(finding.kind == "possible_duplicate" for finding in report.hard_blockers))

    async def test_agent_check_companion_pairs_are_not_blockers(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        report = await AgentModpackService(ReviewFacade()).agent_check(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "xaeros-minimap", "role": "utility", "reason_selected": "Minimap"},
                    {"slug": "xaeros-world-map", "role": "utility", "reason_selected": "World map"},
                    {"slug": "travelersbackpack", "role": "utility", "reason_selected": "Mobile storage"},
                    {"slug": "toms-storage", "role": "utility", "reason_selected": "Base storage"},
                ]
            ),
            pack_design=infer_pack_design_from_concept("cozy farming peaceful village cooking"),
        )

        self.assertIn(report.build_permission, {"allowed", "allowed_with_warnings"})
        self.assertFalse(report.hard_blockers)
        blocker_mods = {mod for finding in report.hard_blockers for mod in finding.affected_mods}
        self.assertFalse({"xaeros-minimap", "xaeros-world-map", "travelersbackpack", "toms-storage"} & blocker_mods)

    async def test_agent_check_stale_low_signal_is_warning(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        report = await AgentModpackService(ReviewFacade()).agent_check(
            self.selected([{"slug": "lava-chicken-disc", "role": "theme", "reason_selected": "Novelty disc"}])
        )

        self.assertNotEqual(report.build_permission, "blocked")
        self.assertTrue(any(finding.kind == "stale_or_low_signal" for finding in report.warnings))

    async def test_missing_performance_foundation_creates_high_issue_and_search_terms(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected([{"slug": "when-dungeons-arise", "role": "theme", "reason_selected": "Dungeons"}])
        )

        issues = [issue for issue in report.issues if issue.category == "pillar_coverage"]
        self.assertTrue(any(issue.severity == "high" and "performance" in issue.title.lower() for issue in issues))
        self.assertTrue(any("performance" in term.lower() for term in report.recommended_replacement_searches))

    async def test_duplicate_minimap_warns_but_xaero_pair_is_accepted(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        service = AgentModpackService(ReviewFacade())
        duplicate = await service.review_mod_list(
            self.selected(
                [
                    {"slug": "xaeros-minimap", "role": "utility", "reason_selected": "Navigation"},
                    {"slug": "journeymap", "role": "utility", "reason_selected": "Navigation"},
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                ]
            )
        )
        accepted = await service.review_mod_list(
            self.selected(
                [
                    {"slug": "xaeros-minimap", "role": "utility", "reason_selected": "Minimap"},
                    {"slug": "xaeros-world-map", "role": "utility", "reason_selected": "World map"},
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                ]
            )
        )

        self.assertTrue(any("minimap" in issue.category for issue in duplicate.duplicate_systems))
        self.assertFalse(any("minimap" in issue.category for issue in accepted.duplicate_systems))

    async def test_design_map_duplicates_allow_xaero_pair_but_flag_journeymap_overlap(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept("cozy farming peaceful village cooking")
        service = AgentModpackService(ReviewFacade())
        accepted = await service.review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "xaeros-minimap", "role": "utility", "reason_selected": "Minimap"},
                    {"slug": "xaeros-world-map", "role": "utility", "reason_selected": "World map"},
                ]
            ),
            pack_design=design,
        )
        duplicate = await service.review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "journeymap", "role": "utility", "reason_selected": "Map"},
                    {"slug": "xaeros-minimap", "role": "utility", "reason_selected": "Minimap"},
                ]
            ),
            pack_design=design,
        )

        self.assertFalse(any(issue.category == "duplicate_map_tools" for issue in accepted.cohesion_issues))
        self.assertTrue(any(issue.category == "duplicate_map_tools" for issue in duplicate.cohesion_issues))

    async def test_storage_duplicates_distinguish_mobile_base_and_inventory_qol(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept("cozy farming peaceful village cooking")
        service = AgentModpackService(ReviewFacade())
        complementary = await service.review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "travelersbackpack", "role": "utility", "reason_selected": "Mobile storage"},
                    {"slug": "toms-storage", "role": "utility", "reason_selected": "Base storage"},
                    {"slug": "mouse-tweaks", "role": "utility", "reason_selected": "Inventory QoL"},
                ]
            ),
            pack_design=design,
        )
        duplicate = await service.review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "toms-storage", "role": "utility", "reason_selected": "Base storage"},
                    {"slug": "simple-storage-network", "role": "utility", "reason_selected": "Base storage network"},
                ]
            ),
            pack_design=design,
        )

        self.assertFalse(any(issue.category == "duplicate_storage_networks" for issue in complementary.cohesion_issues))
        self.assertTrue(any(issue.category == "duplicate_storage_networks" for issue in duplicate.cohesion_issues))

    async def test_known_bad_memory_becomes_risky_combination_issue(self):
        from mythweaver.knowledge.compatibility import CompatibilityMemory
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-review-memory"
        settings = ReviewSettings(root)
        CompatibilityMemory(settings.data_dir).record_failed_pack(
            name="Risk",
            minecraft_version="1.20.1",
            loader="fabric",
            mods=["sodium", "iris"],
            failed_stage="validation_launch",
            crash_classification="renderer_shader_conflict",
            suspected_mods=["sodium", "iris"],
            suggested_fixes=["replace one renderer/shader mod"],
            log_paths=[],
        )
        report = await AgentModpackService(ReviewFacade(settings)).review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "iris", "role": "shader_support", "reason_selected": "Shaders"},
                ]
            )
        )

        self.assertTrue(report.risky_combinations)
        self.assertEqual(report.risky_combinations[0].severity, "high")

    async def test_low_download_stale_and_novelty_candidates_are_flagged(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected([{"slug": "lava-chicken-disc", "role": "theme", "reason_selected": "Lava"}])
        )

        categories = {issue.category for issue in report.stale_or_low_signal_mods + report.novelty_or_off_theme_mods}
        self.assertIn("low_signal_mod", categories)
        self.assertIn("stale_mod", categories)
        self.assertIn("novelty_or_off_theme", categories)

    async def test_dependency_impact_reports_added_dependencies(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected([{"slug": "when-dungeons-arise", "role": "theme", "reason_selected": "Dungeons"}])
        )

        self.assertEqual(report.dependency_impact.user_selected_count, 1)
        self.assertGreaterEqual(report.dependency_impact.dependency_added_count, 1)
        self.assertIn("library-b", report.dependency_impact.dependency_added_mods)

    async def test_cloud_ai_review_prompt_contains_original_json_and_instruction(self):
        from mythweaver.handoff import write_cloud_ai_review_prompt
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-review-prompt"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            json.dumps(
                {
                    "name": "Review Prompt Pack",
                    "minecraft_version": "1.20.1",
                    "loader": "fabric",
                    "mods": [{"slug": "lava-chicken-disc", "role": "theme", "reason_selected": "Lava"}],
                }
            ),
            encoding="utf-8",
        )
        selected = self.selected([{"slug": "lava-chicken-disc", "role": "theme", "reason_selected": "Lava"}], name="Review Prompt Pack")
        report = await AgentModpackService(ReviewFacade()).review_mod_list(selected, root, write_prompt=False)

        prompt = write_cloud_ai_review_prompt(selected_path, report, output_dir=root)

        text = prompt.read_text(encoding="utf-8")
        self.assertIn("Return corrected selected_mods.json only", text)
        self.assertIn('"lava-chicken-disc"', text)
        self.assertIn("Do not invent mods", text)

    async def test_review_list_against_design_adds_design_fields(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept("exploration survival worldgen structures map storage atmosphere")
        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "terralith", "role": "theme", "reason_selected": "Worldgen"},
                    {"slug": "xaeros-minimap", "role": "utility", "reason_selected": "Navigation"},
                ]
            ),
            pack_design=design,
            pack_design_path=Path("pack_design.json"),
        )

        self.assertEqual(report.archetype, "exploration_survival")
        self.assertEqual(report.pack_design_path, "pack_design.json")
        self.assertGreaterEqual(report.design_alignment_score, 0)
        self.assertIn("worldgen", report.system_coverage)

    async def test_review_list_against_design_flags_missing_required_systems(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept("expert tech automation chain hard recipes final factory")
        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected([{"slug": "sodium", "role": "foundation", "reason_selected": "Performance"}]),
            pack_design=design,
        )

        self.assertIn("storage_solution", report.missing_required_systems)
        self.assertTrue(any(issue.severity == "high" for issue in report.progression_gaps + report.cohesion_issues))

    async def test_review_list_against_design_flags_forbidden_systems(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept("cozy farming peaceful village cooking")
        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "farmers-delight", "role": "theme", "reason_selected": "Cooking"},
                    {"slug": "from-the-fog", "role": "theme", "reason_selected": "Horror pressure"},
                ]
            ),
            pack_design=design,
        )

        self.assertTrue(report.anti_goal_violations)
        self.assertTrue(any("horror" in issue.title.lower() or "horror" in (issue.detail or "").lower() for issue in report.anti_goal_violations))

    async def test_known_mod_mappings_do_not_misclassify_cozy_world_mods(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept("cozy farming peaceful village cooking beautiful worldgen")
        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "lithium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "ferrite-core", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "farmers-delight-refabricated", "role": "theme", "reason_selected": "Cooking farming"},
                    {"slug": "croptopia", "role": "theme", "reason_selected": "Farming cooking"},
                    {"slug": "naturalist", "role": "theme", "reason_selected": "Animals"},
                    {"slug": "ct-overhaul-village", "role": "theme", "reason_selected": "Villages"},
                    {"slug": "terralith", "role": "theme", "reason_selected": "Worldgen"},
                    {"slug": "chipped", "role": "theme", "reason_selected": "Building blocks"},
                    {"slug": "rechiseled", "role": "theme", "reason_selected": "Decoration"},
                    {"slug": "toms-storage", "role": "utility", "reason_selected": "Storage"},
                    {"slug": "visuality", "role": "theme", "reason_selected": "Visual polish"},
                    {"slug": "ambientsounds", "role": "theme", "reason_selected": "Atmosphere soundscape"},
                ],
                name="Cozy Mapping Pack",
                summary="Cozy farming pack.",
            ),
            pack_design=design,
        )

        coverage = report.system_coverage
        self.assertIn("ct-overhaul-village", coverage["villages"])
        self.assertIn("naturalist", coverage["animals"])
        self.assertIn("terralith", coverage["worldgen"])
        self.assertIn("farmers-delight-refabricated", coverage["cooking"])
        self.assertIn("croptopia", coverage["farming"])
        self.assertIn("toms-storage", coverage["storage_solution"])
        self.assertNotIn("automation", coverage)
        self.assertFalse(any(issue.category == "duplicate_large_worldgen" for issue in report.cohesion_issues))
        self.assertNotEqual(report.build_recommendation, "do_not_build")

    async def test_duplicate_large_worldgen_only_counts_full_overhauls(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        service = AgentModpackService(ReviewFacade())
        design = infer_pack_design_from_concept("cozy farming peaceful village cooking beautiful worldgen")
        healthy = await service.review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "terralith", "role": "theme", "reason_selected": "Worldgen"},
                    {"slug": "ct-overhaul-village", "role": "theme", "reason_selected": "Villages"},
                    {"slug": "naturalist", "role": "theme", "reason_selected": "Animals"},
                ]
            ),
            pack_design=design,
        )
        two = await service.review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "terralith", "role": "theme", "reason_selected": "Worldgen"},
                    {"slug": "regions-unexplored", "role": "theme", "reason_selected": "Worldgen"},
                ]
            ),
            pack_design=design,
        )
        three = await service.review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "terralith", "role": "theme", "reason_selected": "Worldgen"},
                    {"slug": "regions-unexplored", "role": "theme", "reason_selected": "Worldgen"},
                    {"slug": "tectonic", "role": "theme", "reason_selected": "Worldgen"},
                ]
            ),
            pack_design=design,
        )

        self.assertFalse(any(issue.category == "duplicate_large_worldgen" for issue in healthy.cohesion_issues))
        self.assertTrue(any(issue.category == "duplicate_large_worldgen" and issue.severity == "warning" for issue in two.cohesion_issues))
        self.assertTrue(any(issue.category == "duplicate_large_worldgen" for issue in three.cohesion_issues))

    async def test_structure_overstack_excludes_maps_waystones_and_terrain(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept("cozy farming peaceful village cooking beautiful worldgen")
        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "terralith", "role": "theme", "reason_selected": "Terrain"},
                    {"slug": "ct-overhaul-village", "role": "theme", "reason_selected": "Villages"},
                    {"slug": "explorify", "role": "theme", "reason_selected": "Light structures"},
                    {"slug": "xaeros-minimap", "role": "utility", "reason_selected": "Map"},
                    {"slug": "xaeros-world-map", "role": "utility", "reason_selected": "Map"},
                    {"slug": "waystones", "role": "utility", "reason_selected": "Travel"},
                ]
            ),
            pack_design=design,
        )

        overstack = [issue for issue in report.duplicate_systems if issue.category == "structure_overstack"]
        self.assertFalse(overstack)

    async def test_cozy_example_shape_scores_above_70_with_complementary_mods(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept(
            "cozy farming peaceful village cooking beautiful worldgen storage inventory client qol visual polish atmosphere"
        )
        mods = json.loads(Path("examples/cozy_beautiful_world.selected_mods.json").read_text(encoding="utf-8"))["mods"]
        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected(mods, name="Cozy Beautiful World", summary="Cozy farming and building pack."),
            pack_design=design,
        )

        self.assertGreaterEqual(report.score, 70)
        self.assertNotEqual(report.build_recommendation, "do_not_build")
        self.assertFalse(any(issue.category == "duplicate_map_tools" for issue in report.cohesion_issues))
        self.assertFalse(any(issue.category == "duplicate_storage_networks" for issue in report.cohesion_issues))
        self.assertFalse(any(pillar.pillar == "performance_foundation" and pillar.status == "overloaded" for pillar in report.pillars))

    async def test_review_list_against_design_flags_skyblock_worldgen_dependency(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept("skyblock island void quest automation resources")
        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected(
                [
                    {"slug": "terralith", "role": "theme", "reason_selected": "Normal overworld worldgen"},
                    {"slug": "when-dungeons-arise", "role": "theme", "reason_selected": "Normal structures"},
                ]
            ),
            pack_design=design,
        )

        self.assertTrue(any("skyblock" in issue.category for issue in report.pacing_issues + report.cohesion_issues))

    async def test_review_list_against_design_flags_horror_comfort_power_creep(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept("horror survival darkness scarce resources")
        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected(
                [
                    {"slug": "journeymap", "role": "utility", "reason_selected": "Full map reveal"},
                    {"slug": "waystones", "role": "utility", "reason_selected": "Fast travel"},
                    {"slug": "avaritia", "role": "theme", "reason_selected": "Overpowered gear"},
                ]
            ),
            pack_design=design,
        )

        detail = " ".join((issue.detail or "") + " " + issue.title for issue in report.pacing_issues + report.anti_goal_violations).lower()
        self.assertIn("horror", detail)
        self.assertTrue("fast travel" in detail or "map" in detail or "overpowered" in detail)

    async def test_review_list_against_design_flags_vanilla_plus_bloat(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept("vanilla plus enhanced vanilla")
        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected(
                [
                    {"slug": "create", "role": "theme", "reason_selected": "Tech"},
                    {"slug": "botania", "role": "theme", "reason_selected": "Magic"},
                    {"slug": "ars-nouveau", "role": "theme", "reason_selected": "Magic"},
                    {"slug": "when-dungeons-arise", "role": "theme", "reason_selected": "Dungeons"},
                ]
            ),
            pack_design=design,
        )

        self.assertTrue(any("vanilla" in issue.category for issue in report.cohesion_issues + report.pacing_issues))

    async def test_review_list_against_design_flags_expert_tech_without_chain_support(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        design = infer_pack_design_from_concept("expert tech automation hard recipes")
        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected(
                [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "create", "role": "theme", "reason_selected": "Automation"},
                ]
            ),
            pack_design=design,
        )

        self.assertIn("recipe_progression", report.missing_required_systems)
        self.assertIn("storage_solution", report.missing_required_systems)
        self.assertTrue(any(issue.severity == "high" for issue in report.progression_gaps + report.cohesion_issues))

    async def test_design_aware_cloud_prompt_contains_theme_guardrails(self):
        from mythweaver.handoff import write_cloud_ai_review_prompt
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        root = Path.cwd() / "output" / "test-design-aware-review-prompt"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            json.dumps(
                {
                    "name": "Guardrail Pack",
                    "minecraft_version": "1.20.1",
                    "loader": "fabric",
                    "mods": [{"slug": "from-the-fog", "role": "theme", "reason_selected": "Horror"}],
                }
            ),
            encoding="utf-8",
        )
        report = await AgentModpackService(ReviewFacade()).review_mod_list(
            self.selected([{"slug": "from-the-fog", "role": "theme", "reason_selected": "Horror"}], name="Guardrail Pack"),
            pack_design=infer_pack_design_from_concept("cozy farming peaceful village cooking"),
            pack_design_path=root / "pack_design.json",
            write_prompt=False,
        )

        prompt = write_cloud_ai_review_prompt(selected_path, report, output_dir=root)
        text = prompt.read_text(encoding="utf-8")
        self.assertIn("Design alignment score", text)
        self.assertIn("Do not add RPG systems unless the design calls for RPG systems", text)
        self.assertIn("Respect forbidden systems", text)
