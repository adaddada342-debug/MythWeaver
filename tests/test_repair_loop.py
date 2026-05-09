import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.test_agent_selected_workflow import FakeAgentFacade


class RepairLoopTests(unittest.IsolatedAsyncioTestCase):
    def selected_payload(self):
        return {
            "name": "Repair Pack",
            "summary": "A small pack used to exercise repair planning.",
            "minecraft_version": "1.20.1",
            "loader": "fabric",
            "mods": [
                {"slug": "sodium", "role": "foundation", "reason_selected": "Renderer optimization"},
                {"slug": "iris", "role": "shader_support", "reason_selected": "Shader support"},
                {"slug": "when-dungeons-arise", "role": "theme", "reason_selected": "Dungeons"},
            ],
        }

    def write_report(self, root: Path, log_text: str, *, status: str = "failed") -> Path:
        from mythweaver.schemas.contracts import AgentPackReport, ValidationReport
        from mythweaver.validation.crash_analyzer import analyze_failure

        root.mkdir(parents=True, exist_ok=True)
        log_path = root / "latest.log"
        log_path.write_text(log_text, encoding="utf-8")
        analysis = analyze_failure(log_text)
        report = AgentPackReport.model_validate(
            {
                "run_id": "repair-test",
                "status": "completed",
                "name": "Repair Pack",
                "summary": "A small pack used to exercise repair planning.",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "validation_status": status,
                "logs_collected": [str(log_path)],
                "crash_analysis": analysis.model_dump(mode="json"),
                "launch_validation": ValidationReport(
                    status=status,
                    logs_collected=[str(log_path)],
                    analysis=analysis,
                    suspected_mods=["sodium"] if "sodium" in log_text.lower() else [],
                    suggested_actions=analysis.repair_candidates,
                ).model_dump(mode="json"),
                "next_actions": ["repair_plan"],
            }
        )
        report_path = root / "generation_report.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report_path

    async def test_repair_plan_missing_dependency_suggests_add_dependency_without_mutation(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-repair-missing-dependency"
        report_path = self.write_report(root, "Mod when-dungeons-arise requires dependency library-b to install")

        repair = await AgentModpackService(FakeAgentFacade()).create_repair_plan(report_path=report_path)

        self.assertEqual(repair.crash_classification, "missing_dependency")
        self.assertTrue(any(option.action_type == "add_missing_dependency" for option in repair.repair_options))
        self.assertTrue((root / "repair_report.json").is_file())
        self.assertTrue((root / "repair_report.md").is_file())

    async def test_repair_plan_duplicate_mod_id_suggests_duplicate_removal(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        report_path = self.write_report(Path.cwd() / "output" / "test-repair-duplicate", "Duplicate mod ID sodium was found")

        repair = await AgentModpackService(FakeAgentFacade()).create_repair_plan(report_path=report_path)

        self.assertEqual(repair.crash_classification, "duplicate_mod")
        self.assertIn("remove_duplicate_system", {option.action_type for option in repair.repair_options})

    async def test_repair_plan_mixin_failure_extracts_suspect_and_marks_risk(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        report_path = self.write_report(Path.cwd() / "output" / "test-repair-mixin", "Mixin apply failed in sodium renderer")

        repair = await AgentModpackService(FakeAgentFacade()).create_repair_plan(report_path=report_path)

        self.assertEqual(repair.crash_classification, "mixin_failure")
        self.assertIn("sodium", repair.suspected_mods)
        self.assertTrue(any(option.action_type in {"remove_mod", "replace_mod"} for option in repair.repair_options))
        self.assertTrue(all(option.risk_level in {"medium", "high"} for option in repair.repair_options if option.action_type != "mark_manual_review_required"))

    async def test_repair_plan_java_mismatch_does_not_primary_remove_mods(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        report_path = self.write_report(Path.cwd() / "output" / "test-repair-java", "UnsupportedClassVersionError Java version")

        repair = await AgentModpackService(FakeAgentFacade()).create_repair_plan(report_path=report_path)

        self.assertEqual(repair.crash_classification, "java_mismatch")
        self.assertNotIn("remove_mod", {option.action_type for option in repair.repair_options[:1]})
        self.assertTrue(any("Java" in action for action in repair.next_actions))

    async def test_repair_plan_unknown_crash_requires_manual_review(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        report_path = self.write_report(Path.cwd() / "output" / "test-repair-unknown", "Something exploded without recognizable evidence")

        repair = await AgentModpackService(FakeAgentFacade()).create_repair_plan(report_path=report_path)

        self.assertEqual(repair.crash_classification, "unknown")
        self.assertIn("mark_manual_review_required", {option.action_type for option in repair.repair_options})

    async def test_apply_repair_remove_mod_preserves_original_and_adds_changelog(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import RepairOption, RepairReport, SelectedModList

        root = Path.cwd() / "output" / "test-apply-remove"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(json.dumps(self.selected_payload()), encoding="utf-8")
        repair_path = root / "repair_report.json"
        RepairReport(
            pack_name="Repair Pack",
            source_report_path=str(root / "generation_report.json"),
            validation_status="failed",
            failed_stage="validation_launch",
            crash_classification="mixin_failure",
            suspected_mods=["iris"],
            repair_options=[
                RepairOption(id="repair_001", action_type="remove_mod", target_slug="iris", reason="Crash references iris", confidence=0.7, risk_level="high")
            ],
            confidence=0.7,
            next_actions=[],
        ).model_dump_json()
        repair_path.write_text(
            RepairReport(
                pack_name="Repair Pack",
                source_report_path=str(root / "generation_report.json"),
                validation_status="failed",
                failed_stage="validation_launch",
                crash_classification="mixin_failure",
                suspected_mods=["iris"],
                repair_options=[
                    RepairOption(id="repair_001", action_type="remove_mod", target_slug="iris", reason="Crash references iris", confidence=0.7, risk_level="high")
                ],
                confidence=0.7,
                next_actions=[],
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )
        output_path = root / "selected_mods.repaired.json"

        result = await AgentModpackService(FakeAgentFacade()).apply_repair_option(
            repair_path,
            option_id="repair_001",
            selected_mods_path=selected_path,
            output_path=output_path,
        )

        original = SelectedModList.model_validate_json(selected_path.read_text(encoding="utf-8"))
        repaired = SelectedModList.model_validate_json(output_path.read_text(encoding="utf-8"))
        self.assertIn("iris", {mod.slug for mod in original.mods})
        self.assertNotIn("iris", {mod.slug for mod in repaired.mods})
        self.assertEqual(repaired.repair_changelog[0]["option_id"], "repair_001")
        self.assertEqual(result["changed"], True)

    async def test_apply_repair_replace_mod_and_add_dependency_keep_schema_valid(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import RepairOption, RepairReport, SelectedModList

        root = Path.cwd() / "output" / "test-apply-replace-dependency"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(json.dumps(self.selected_payload()), encoding="utf-8")
        replace_path = root / "replace_report.json"
        RepairReport(
            pack_name="Repair Pack",
            source_report_path=str(root / "generation_report.json"),
            validation_status="failed",
            failed_stage="validation_launch",
            crash_classification="mixin_failure",
            suspected_mods=["iris"],
            repair_options=[
                RepairOption(
                    id="repair_replace",
                    action_type="replace_mod",
                    target_slug="iris",
                    replacement_candidates=[{"slug": "sodium", "reason": "Known compatible renderer foundation"}],
                    reason="Replace unstable shader support",
                    confidence=0.5,
                    risk_level="high",
                ),
                RepairOption(
                    id="repair_dependency",
                    action_type="add_missing_dependency",
                    target_slug="library-b",
                    reason="Missing required dependency",
                    confidence=0.8,
                    risk_level="low",
                ),
            ],
            confidence=0.6,
            next_actions=[],
        ).model_dump_json()
        replace_path.write_text(
            RepairReport(
                pack_name="Repair Pack",
                source_report_path=str(root / "generation_report.json"),
                validation_status="failed",
                failed_stage="validation_launch",
                crash_classification="mixin_failure",
                suspected_mods=["iris"],
                repair_options=[
                    RepairOption(
                        id="repair_replace",
                        action_type="replace_mod",
                        target_slug="iris",
                        replacement_candidates=[{"slug": "sodium", "reason": "Known compatible renderer foundation"}],
                        reason="Replace unstable shader support",
                        confidence=0.5,
                        risk_level="high",
                    ),
                    RepairOption(
                        id="repair_dependency",
                        action_type="add_missing_dependency",
                        target_slug="library-b",
                        reason="Missing required dependency",
                        confidence=0.8,
                        risk_level="low",
                    ),
                ],
                confidence=0.6,
                next_actions=[],
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )

        replaced_path = root / "selected_mods.replaced.json"
        await AgentModpackService(FakeAgentFacade()).apply_repair_option(
            replace_path,
            option_id="repair_replace",
            selected_mods_path=selected_path,
            output_path=replaced_path,
        )
        repaired = SelectedModList.model_validate_json(replaced_path.read_text(encoding="utf-8"))
        self.assertNotIn("iris", {mod.slug for mod in repaired.mods})
        self.assertIn("sodium", {mod.slug for mod in repaired.mods})

        dependency_path = root / "selected_mods.dependency.json"
        await AgentModpackService(FakeAgentFacade()).apply_repair_option(
            replace_path,
            option_id="repair_dependency",
            selected_mods_path=selected_path,
            output_path=dependency_path,
        )
        repaired_dependency = SelectedModList.model_validate_json(dependency_path.read_text(encoding="utf-8"))
        dependency = next(mod for mod in repaired_dependency.mods if mod.slug == "library-b")
        self.assertEqual(dependency.role, "dependency")
        self.assertTrue(dependency.required)

    async def test_repair_memory_records_generation_and_appears_in_future_plan(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-repair-memory"
        report_path = self.write_report(root, "Mixin apply failed in sodium renderer")
        service = AgentModpackService(FakeAgentFacade())
        service.memory.root = root / "data" / "knowledge" / "local"
        service.memory.path = service.memory.root / "compatibility_memory.json"

        first = await service.create_repair_plan(report_path=report_path)
        second = await service.create_repair_plan(report_path=report_path)

        self.assertTrue(first.repair_options)
        self.assertTrue(second.memory_advisories)


class RepairSurfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_rest_and_mcp_tools_expose_repair_service_methods(self):
        from mythweaver.mcp.server import call_tool, tool_definitions
        from mythweaver.schemas.contracts import RepairReport

        class StubFacade:
            async def create_repair_plan(self, **kwargs):
                return RepairReport(pack_name="Pack", source_report_path="report.json", validation_status="failed", repair_options=[])

            async def apply_repair_option(self, *args, **kwargs):
                return {"changed": True}

        names = {tool["name"] for tool in tool_definitions()}
        self.assertIn("create_repair_plan", names)
        self.assertIn("apply_repair_option", names)
        plan = await call_tool(StubFacade(), "create_repair_plan", {"report_path": "report.json"})
        applied = await call_tool(
            StubFacade(),
            "apply_repair_option",
            {"repair_report": "repair_report.json", "option_id": "repair_001", "selected_mods": "selected.json", "output": "out.json"},
        )
        self.assertEqual(plan.pack_name, "Pack")
        self.assertTrue(applied["changed"])

    def test_cli_help_commands_exist(self):
        from mythweaver.cli.main import _fallback_main

        for command in ["repair-plan", "apply-repair", "repair-pack"]:
            stdout = StringIO()
            with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
                _fallback_main([command, "--help"])
            self.assertEqual(raised.exception.code, 0)
            self.assertIn(command, stdout.getvalue())
