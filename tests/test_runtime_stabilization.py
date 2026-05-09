import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.test_agent_selected_workflow import FakeAgentFacade, FakeAgentModrinth, project_payload
from tests.test_pipeline_discovery import version_payload


HWG_AZURELIB_CRASH = """
java.lang.RuntimeException: Could not execute entrypoint stage 'main' due to errors, provided by 'hwg'
Caused by: java.lang.NoClassDefFoundError: mod/azure/azurelib/animatable/GeoItem
Caused by: java.lang.ClassNotFoundException: mod.azure.azurelib.animatable.GeoItem
"""


IPN_KOTLIN_CRASH = """
java.lang.RuntimeException: Exception in client tick
Caused by: kotlin.reflect.jvm.internal.KotlinReflectionInternalError: Function 'matches' has no resolved call
    at org.anti_ad.mc.ipnext.inventory.ClientEventHandler.onJoinWorld(ClientEventHandler.kt:42)
"""


class RuntimeModrinth(FakeAgentModrinth):
    def __init__(self):
        super().__init__()
        extra = {
            "hwg": project_payload("hwg-id", slug="hwg", title="Happiness is a Warm Gun", categories=["combat"]),
            "azurelib": project_payload("azurelib-id", slug="azurelib", title="AzureLib", categories=["library"]),
            "inventory-profiles-next": project_payload(
                "ipn-id", slug="inventory-profiles-next", title="Inventory Profiles Next", categories=["utility"]
            ),
            "inventoryprofilesnext": project_payload(
                "ipn-id", slug="inventory-profiles-next", title="Inventory Profiles Next", categories=["utility"]
            ),
            "libipn": project_payload("libipn-id", slug="libipn", title="libIPN", categories=["library"]),
            "fabric-language-kotlin": project_payload(
                "flk-id", slug="fabric-language-kotlin", title="Fabric Language Kotlin", categories=["library"]
            ),
            "emi": project_payload("emi-id", slug="emi", title="EMI", categories=["utility"]),
            "mouse-tweaks": project_payload("mouse-id", slug="mouse-tweaks", title="Mouse Tweaks", categories=["utility"]),
        }
        self.projects.update(extra)
        self.projects.update({project["id"]: project for project in extra.values()})
        for slug, project in extra.items():
            project_id = project["id"]
            self.versions[slug] = [version_payload(project_id)]
            self.versions[project_id] = [version_payload(project_id)]


class RuntimeFacade(FakeAgentFacade):
    def __init__(self):
        super().__init__()
        self.modrinth = RuntimeModrinth()


class RuntimeStabilizationTests(unittest.IsolatedAsyncioTestCase):
    def selected(self, mods=None):
        from mythweaver.schemas.contracts import SelectedModList

        return SelectedModList.model_validate(
            {
                "name": "Runtime Pack",
                "summary": "Combat and QoL pack with fallback systems.",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": mods
                or [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                    {"slug": "hwg", "role": "theme", "reason_selected": "Gun combat fantasy"},
                    {"slug": "inventory-profiles-next", "role": "utility", "reason_selected": "Inventory QoL"},
                    {"slug": "libipn", "role": "utility", "reason_selected": "Inventory Profiles dependency"},
                    {"slug": "emi", "role": "utility", "reason_selected": "Recipe and inventory support"},
                    {"slug": "mouse-tweaks", "role": "utility", "reason_selected": "Inventory QoL fallback"},
                ],
            }
        )

    def test_analyze_crash_identifies_hwg_azurelib_runtime_mismatch(self):
        from mythweaver.pipeline.crash_analysis import analyze_crash_report

        report = analyze_crash_report(HWG_AZURELIB_CRASH, selected=self.selected(), crash_report_path="crash.txt")

        self.assertEqual(report.status, "identified")
        self.assertEqual(report.crashing_mod_id, "hwg")
        self.assertEqual(report.repair_recommendation, "replace_mod")
        self.assertTrue(any(finding.kind == "dependency_version_mismatch" for finding in report.findings))
        self.assertTrue(any(finding.kind == "external_dependency_risk" for finding in report.findings))
        self.assertTrue(any(finding.missing_mod_id == "azurelib" for finding in report.findings))

    def test_analyze_crash_identifies_inventory_profiles_kotlin_world_join(self):
        from mythweaver.pipeline.crash_analysis import analyze_crash_report

        report = analyze_crash_report(IPN_KOTLIN_CRASH, selected=self.selected(), crash_report_path="crash.txt")

        self.assertEqual(report.status, "identified")
        self.assertEqual(report.crashing_mod_id, "inventoryprofilesnext")
        self.assertEqual(report.repair_recommendation, "remove_mod")
        self.assertTrue(any(finding.kind == "kotlin_reflection_error" for finding in report.findings))
        self.assertTrue(any(finding.kind == "world_join_crash" for finding in report.findings))
        suspects = {mod for finding in report.findings for mod in finding.suspected_mods}
        self.assertIn("inventoryprofilesnext", suspects)
        self.assertIn("libipn", suspects)
        self.assertIn("fabric-language-kotlin", suspects)

    def test_crash_prompt_is_written(self):
        from mythweaver.handoff import write_cloud_ai_crash_repair_prompt
        from mythweaver.pipeline.crash_analysis import analyze_crash_report

        root = Path.cwd() / "output" / "test-crash-prompt"
        report = analyze_crash_report(HWG_AZURELIB_CRASH, selected=self.selected(), crash_report_path="crash.txt")
        prompt = write_cloud_ai_crash_repair_prompt(report, output_dir=root)

        self.assertTrue(prompt.is_file())
        text = prompt.read_text(encoding="utf-8")
        self.assertIn("hard facts from the crash", text)
        self.assertIn("prefer removing/replacing optional risky mods", text)
        self.assertIn("preserve the pack fantasy", text)

    async def test_stabilize_pack_manual_crash_removes_optional_mod_with_audit(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-stabilize-manual"
        crash = root / "crash-reports" / "crash.txt"
        crash.parent.mkdir(parents=True, exist_ok=True)
        crash.write_text(HWG_AZURELIB_CRASH, encoding="utf-8")

        report = await AgentModpackService(RuntimeFacade()).stabilize_pack(
            self.selected(),
            root,
            max_attempts=2,
            manual_crash_report=crash,
            no_launch=True,
        )

        self.assertEqual(report.status, "needs_manual_review")
        self.assertTrue((root / "selected_mods.previous.json").is_file())
        self.assertTrue((root / "selected_mods.stabilized.json").is_file())
        self.assertTrue((root / "stabilization_report.json").is_file())
        self.assertTrue((root / "removed_mods.json").is_file())
        stabilized = json.loads((root / "selected_mods.stabilized.json").read_text(encoding="utf-8"))
        self.assertNotIn("hwg", {entry.get("slug") for entry in stabilized["mods"]})
        removed = json.loads((root / "removed_mods.json").read_text(encoding="utf-8"))
        self.assertEqual(removed[0]["slug_or_id"], "hwg")
        self.assertIn("runtime crash", removed[0]["reason"])
        self.assertLessEqual(len(report.attempts), 2)
        self.assertTrue(report.attempts[0].removed_mods)

    async def test_launch_check_manual_required_and_crash_report_failure(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        service = AgentModpackService(RuntimeFacade())
        manual = await service.launch_check(self.selected(), Path("output") / "test-launch-check", manual=True)
        self.assertEqual(manual.status, "manual_required")
        self.assertIn("Dry-run is not playable proof", manual.summary)

        root = Path.cwd() / "output" / "test-launch-check-crash"
        crash = root / "crash.txt"
        root.mkdir(parents=True, exist_ok=True)
        crash.write_text(IPN_KOTLIN_CRASH, encoding="utf-8")
        failed = await service.launch_check(self.selected(), root, crash_report=crash)
        self.assertEqual(failed.status, "failed")
        self.assertIsNotNone(failed.crash_analysis)
        self.assertEqual(failed.crash_analysis.crashing_mod_id, "inventoryprofilesnext")

    def test_cli_help_includes_runtime_commands(self):
        from mythweaver.cli.main import _fallback_main

        for command in ["analyze-crash", "stabilize-pack", "launch-check"]:
            stdout = StringIO()
            with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
                _fallback_main([command, "--help"])

            self.assertEqual(raised.exception.code, 0)

    def test_agent_workflow_prompt_mentions_runtime_stabilization(self):
        from mythweaver.handoff import write_agent_workflow_prompt

        root = Path.cwd() / "output" / "test-runtime-workflow"
        concept = root / "concept.md"
        concept.parent.mkdir(parents=True, exist_ok=True)
        concept.write_text("# Runtime Fantasy\n\nMake it playable.", encoding="utf-8")
        report = write_agent_workflow_prompt(concept, concept.read_text(encoding="utf-8"), output_dir=root)

        text = Path(report.prompt_path).read_text(encoding="utf-8")
        self.assertIn("stabilize-pack", text)
        self.assertIn("dry-run is not final proof", text)
        self.assertIn("Do not ask the user to manually debug stacktraces", text)

    def test_readme_mentions_runtime_stabilization(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("Runtime stabilization", readme)
        self.assertIn("verify-list checks metadata/installability", readme)
        self.assertIn("build dry-run checks packaging", readme)
        self.assertIn("stabilize-pack", readme)
