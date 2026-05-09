import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.test_agent_selected_workflow import FakeAgentFacade


class HudHandoffTests(unittest.IsolatedAsyncioTestCase):
    def test_hud_command_exists_and_shows_help(self):
        from mythweaver.cli.main import _fallback_main

        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            _fallback_main(["hud", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("terminal hud", stdout.getvalue().lower())

    def test_cloud_handoff_prompt_generation_from_plain_concept(self):
        from mythweaver.handoff import create_cloud_handoff_bundle

        root = Path.cwd() / "output" / "test-handoff-concept"
        result = create_cloud_handoff_bundle(
            concept="medieval survival with dangerous nights and castles",
            output_dir=root,
            minecraft_version="1.20.1",
            loader="fabric",
            size="medium",
            performance_priority="balanced",
            shaders="recommendations only",
            avoid_terms="guns, space",
        )

        request = Path(result["cloud_ai_request"])
        self.assertTrue(request.is_file())
        text = request.read_text(encoding="utf-8")
        self.assertIn("valid JSON only", text)
        self.assertIn("selected_mods.json", text)
        self.assertTrue((root / "selected_mods.schema.json").is_file())
        self.assertTrue((root / "example_selected_mods.json").is_file())
        self.assertTrue((root / "README_FOR_AI.md").is_file())

    def test_cloud_handoff_files_exclude_secrets_and_generated_mods(self):
        from mythweaver.handoff import create_cloud_handoff_bundle

        root = Path.cwd() / "output" / "test-handoff-secrets"
        create_cloud_handoff_bundle(
            concept="quiet fantasy villages",
            output_dir=root,
            minecraft_version="1.20.1",
            loader="fabric",
            size="small",
            performance_priority="high",
            shaders="no",
            avoid_terms="",
        )

        combined = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*") if path.is_file())
        self.assertNotIn("MYTHWEAVER_AI_API_KEY", combined)
        self.assertNotIn(".env", combined)
        self.assertNotIn(".jar", combined)
        self.assertNotIn("cache.sqlite3", combined)

    def test_selected_mods_validation_failure_generates_cloud_ai_fix_prompt(self):
        from mythweaver.handoff import validate_selected_mods_file

        root = Path.cwd() / "output" / "test-handoff-invalid"
        root.mkdir(parents=True, exist_ok=True)
        invalid = root / "selected_mods.json"
        invalid.write_text('{"name": "Broken"}', encoding="utf-8")

        result = validate_selected_mods_file(invalid, output_dir=root)

        self.assertFalse(result["valid"])
        prompt = root / "cloud_ai_fix_selected_mods_prompt.md"
        self.assertTrue(prompt.is_file())
        self.assertIn("That JSON file is not in the format MythWeaver expects", prompt.read_text(encoding="utf-8"))

    async def test_verify_list_failure_generates_cloud_ai_fix_prompt(self):
        from mythweaver.handoff import write_cloud_ai_fix_selected_mods_prompt
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import SelectedModList

        root = Path.cwd() / "output" / "test-handoff-verify-fail"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            json.dumps(
                {
                    "name": "Broken Compatibility",
                    "minecraft_version": "1.20.1",
                    "loader": "fabric",
                    "mods": [{"slug": "forge-only"}],
                }
            ),
            encoding="utf-8",
        )
        selected = SelectedModList.model_validate_json(selected_path.read_text(encoding="utf-8"))
        report = await AgentModpackService(FakeAgentFacade()).verify_mod_list(selected)

        prompt = write_cloud_ai_fix_selected_mods_prompt(selected_path, output_dir=root, verify_report=report)

        self.assertTrue(prompt.is_file())
        text = prompt.read_text(encoding="utf-8")
        self.assertIn("forge-only", text)
        self.assertIn("return corrected selected_mods.json only", text)

    async def test_build_failure_generates_actionable_cloud_ai_prompt(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import SelectedModList

        root = Path.cwd() / "output" / "test-handoff-build-fail"
        selected = SelectedModList.model_validate(
            {
                "name": "Broken Build",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": [{"slug": "forge-only"}],
            }
        )

        report = await AgentModpackService(FakeAgentFacade()).build_from_list(selected, root, download=False)

        self.assertEqual(report.status, "failed")
        prompt = root / "cloud_ai_fix_selected_mods_prompt.md"
        self.assertTrue(prompt.is_file())
        self.assertIn("Some selected mods need extra mods or have incompatible requirements", prompt.read_text(encoding="utf-8"))

    async def test_repair_plan_generates_cloud_ai_repair_prompt(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from tests.test_repair_loop import RepairLoopTests

        helper = RepairLoopTests()
        root = Path.cwd() / "output" / "test-handoff-repair-prompt"
        report_path = helper.write_report(root, "Mixin apply failed in sodium renderer")

        await AgentModpackService(FakeAgentFacade()).create_repair_plan(report_path=report_path)

        prompt = root / "cloud_ai_repair_prompt.md"
        self.assertTrue(prompt.is_file())
        self.assertIn("repair_report summary", prompt.read_text(encoding="utf-8").lower())

    async def test_prism_config_check_flow_returns_clear_skipped_message(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from tests.test_launch_validation_memory import MemorySettings, ValidationFacade

        root = Path.cwd() / "output" / "test-handoff-prism-check"
        pack = root / "pack"
        pack.mkdir(parents=True, exist_ok=True)
        report = await AgentModpackService(ValidationFacade(MemorySettings(root))).validate_pack(
            pack,
            check_config_only=True,
        )

        self.assertEqual(report.status, "skipped")
        self.assertIn("Prism", report.details)
        self.assertTrue(report.next_actions or report.suggested_actions)

    def test_hud_fallback_text_includes_main_menu_and_commands(self):
        from mythweaver.cli.hud import render_hud_overview

        text = render_hud_overview()

        self.assertIn("Build a pack from a selected_mods.json", text)
        self.assertIn("python -m mythweaver.cli.main build-from-list", text)
        self.assertIn("python -m mythweaver.cli.main handoff export", text)

    def test_handoff_help_command_exists(self):
        from mythweaver.cli.main import _fallback_main

        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            _fallback_main(["handoff", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("export", stdout.getvalue())
        self.assertIn("validate", stdout.getvalue())
        self.assertIn("import", stdout.getvalue())
