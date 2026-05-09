import json
import unittest
from pathlib import Path

from tests.test_agent_selected_workflow import FakeAgentFacade


class MemorySettings:
    def __init__(self, root: Path, *, validation_enabled=False, prism_path=None, prism_root=None):
        self.data_dir = root / "data"
        self.output_dir = root / "output"
        self.cache_db = root / "cache.sqlite3"
        self.modrinth_user_agent = "test"
        self.validation_enabled = validation_enabled
        self.prism_path = prism_path
        self.prism_root = prism_root
        self.prism_profile = None
        self.prism_executable_path = prism_path
        self.prism_instances_path = prism_root
        self.prism_account_name = None
        self.launch_timeout_seconds = 1
        self.java_path = None


class ValidationFacade(FakeAgentFacade):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.validation_calls = []

    def validate_launch(self, instance_id):
        from mythweaver.schemas.contracts import ValidationReport

        self.validation_calls.append(instance_id)
        return ValidationReport(status="passed", launched=True, details="Mock launch passed.")


class LaunchValidationMemoryTests(unittest.IsolatedAsyncioTestCase):
    def selected_list(self):
        from mythweaver.schemas.contracts import SelectedModList

        return SelectedModList.model_validate(
            {
                "name": "Memory Pack",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": [
                    {"slug": "sodium", "role": "foundation"},
                    {"slug": "lithium", "role": "foundation"},
                    {"slug": "iris", "role": "shader_support"},
                ],
            }
        )

    async def test_validate_pack_skips_clearly_when_prism_is_not_configured(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-validation-skip"
        service = AgentModpackService(ValidationFacade(MemorySettings(root)))

        report = await service.validate_pack(root / "pack")

        self.assertEqual(report.status, "skipped")
        self.assertFalse(report.launched)
        self.assertIn("Prism", report.details)

    async def test_validate_pack_collects_latest_log_and_crash_report(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-validation-logs"
        pack_dir = root / "pack"
        log_dir = pack_dir / "instances" / "memory-pack" / ".minecraft" / "logs"
        crash_dir = pack_dir / "instances" / "memory-pack" / ".minecraft" / "crash-reports"
        log_dir.mkdir(parents=True, exist_ok=True)
        crash_dir.mkdir(parents=True, exist_ok=True)
        latest = log_dir / "latest.log"
        crash = crash_dir / "crash.txt"
        latest.write_text("Mod duplicate id found\n", encoding="utf-8")
        crash.write_text("Duplicate mod ID sodium\n", encoding="utf-8")

        service = AgentModpackService(ValidationFacade(MemorySettings(root)))
        report = await service.validate_pack(pack_dir)

        self.assertIn(str(latest), report.logs_collected)
        self.assertEqual(report.crash_report_path, str(crash))
        self.assertEqual(report.analysis.classification, "duplicate_mod")

    def test_crash_analyzer_classifies_missing_dependency_duplicate_and_mixin(self):
        from mythweaver.validation.crash_analyzer import analyze_failure

        self.assertEqual(analyze_failure("Mod A requires dependency B to install").classification, "missing_dependency")
        self.assertEqual(analyze_failure("Duplicate mod ID sodium").classification, "duplicate_mod")
        self.assertEqual(analyze_failure("Mixin apply failed for Renderer").classification, "mixin_failure")

    def test_crash_analyzer_classifies_renderer_and_memory_failures(self):
        from mythweaver.validation.crash_analyzer import analyze_failure

        self.assertEqual(analyze_failure("Iris shader renderer pipeline failed").classification, "renderer_shader_conflict")
        self.assertEqual(analyze_failure("java.lang.OutOfMemoryError: Java heap space").classification, "out_of_memory")

    async def test_successful_pack_writes_compatibility_memory(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-memory-success"
        prism = root / "PrismLauncher.exe"
        prism.parent.mkdir(parents=True, exist_ok=True)
        prism.write_text("", encoding="utf-8")
        service = AgentModpackService(ValidationFacade(MemorySettings(root, validation_enabled=True, prism_path=prism, prism_root=root)))

        report = await service.build_from_list(
            self.selected_list(),
            root / "pack",
            download=False,
            validate_launch=True,
        )

        memory_file = root / "data" / "knowledge" / "local" / "compatibility_memory.json"
        data = json.loads(memory_file.read_text(encoding="utf-8"))
        self.assertEqual(report.validation_status, "passed")
        self.assertTrue(data["successful_packs"])
        self.assertEqual(data["successful_packs"][0]["source"], "automatic_launch_validation")

    async def test_failed_pack_writes_compatibility_memory(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import ValidationReport

        class FailingFacade(ValidationFacade):
            def validate_launch(self, instance_id):
                from mythweaver.validation.crash_analyzer import analyze_failure

                return ValidationReport(
                    status="failed",
                    launched=True,
                    details="Mock launch failed.",
                    analysis=analyze_failure("Mixin apply failed for sodium"),
                )

        root = Path.cwd() / "output" / "test-memory-failure"
        prism = root / "PrismLauncher.exe"
        prism.parent.mkdir(parents=True, exist_ok=True)
        prism.write_text("", encoding="utf-8")
        service = AgentModpackService(FailingFacade(MemorySettings(root, validation_enabled=True, prism_path=prism, prism_root=root)))

        report = await service.build_from_list(self.selected_list(), root / "pack", download=False, validate_launch=True)

        data = json.loads((root / "data" / "knowledge" / "local" / "compatibility_memory.json").read_text(encoding="utf-8"))
        self.assertEqual(report.validation_status, "failed")
        self.assertEqual(data["failed_packs"][0]["crash_classification"], "mixin_failure")

    async def test_verify_list_warns_about_known_bad_and_boosts_known_good_stack(self):
        from mythweaver.knowledge.compatibility import CompatibilityMemory
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-memory-hints"
        settings = MemorySettings(root)
        memory = CompatibilityMemory(settings.data_dir)
        memory.record_manual_success(
            name="Good Stack",
            minecraft_version="1.20.1",
            loader="fabric",
            mods=["sodium", "lithium", "iris"],
            note="manual success",
        )
        memory.record_failed_pack(
            name="Bad Stack",
            minecraft_version="1.20.1",
            loader="fabric",
            mods=["sodium", "iris"],
            failed_stage="validation_launch",
            crash_classification="renderer_shader_conflict",
            suspected_mods=["sodium", "iris"],
            suggested_fixes=["try updated renderer stack"],
            log_paths=[],
        )

        report = await AgentModpackService(ValidationFacade(settings)).verify_mod_list(self.selected_list())

        self.assertTrue(report.known_good_matches)
        self.assertTrue(report.known_risk_matches)
        self.assertGreater(report.memory_confidence_adjustment, 0)
        self.assertTrue(report.compatibility_warnings)

    async def test_memory_does_not_override_official_verification(self):
        from mythweaver.knowledge.compatibility import CompatibilityMemory
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import SelectedModList

        root = Path.cwd() / "output" / "test-memory-advisory-only"
        settings = MemorySettings(root)
        CompatibilityMemory(settings.data_dir).record_manual_success(
            name="Old Forge Success",
            minecraft_version="1.20.1",
            loader="fabric",
            mods=["forge-only"],
            note="Advisory memory must not override Modrinth compatibility.",
        )
        selected = SelectedModList.model_validate(
            {
                "name": "Advisory Only",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": [{"slug": "forge-only", "role": "theme"}],
            }
        )

        report = await AgentModpackService(ValidationFacade(settings)).verify_mod_list(selected)

        self.assertTrue(report.rejected_mods)
        self.assertIn("no_compatible_installable_version", {rejection.reason for rejection in report.rejected_mods})

    async def test_search_inspect_compare_include_memory_hints(self):
        from mythweaver.knowledge.compatibility import CompatibilityMemory
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-memory-search"
        settings = MemorySettings(root)
        CompatibilityMemory(settings.data_dir).record_manual_success(
            name="Good Stack",
            minecraft_version="1.20.1",
            loader="fabric",
            mods=["sodium", "lithium", "iris"],
            note="manual success",
        )
        service = AgentModpackService(ValidationFacade(settings))

        search = await service.search_mods("sodium", loader="fabric", minecraft_version="1.20.1")
        inspect = await service.inspect_mod("sodium", loader="fabric", minecraft_version="1.20.1")
        compare = await service.compare_mods(["sodium"], loader="fabric", minecraft_version="1.20.1")

        self.assertTrue(search["results"][0]["local_memory"]["known_good_matches"])
        self.assertTrue(inspect["local_memory"]["known_good_matches"])
        self.assertTrue(compare["candidates"][0]["local_memory"]["known_good_matches"])

    async def test_build_from_list_validate_launch_updates_report(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-build-validate"
        prism = root / "PrismLauncher.exe"
        prism.parent.mkdir(parents=True, exist_ok=True)
        prism.write_text("", encoding="utf-8")
        service = AgentModpackService(ValidationFacade(MemorySettings(root, validation_enabled=False, prism_path=prism, prism_root=root)))

        report = await service.build_from_list(self.selected_list(), root / "pack", download=False, validate_launch=True)

        self.assertEqual(report.validation_status, "passed")
        self.assertIsNotNone(report.launch_validation)
        self.assertTrue(report.compatibility_memory_updates)

    def test_kingdoms_after_dark_manual_success_example_is_manual_not_automatic(self):
        path = Path("docs/examples/compatibility_memory/kingdoms-after-dark-manual-success.json")
        data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(data["source"], "user_manual_validation")
        self.assertEqual(data["validation_status"], "manual_success")
        self.assertNotEqual(data["source"], "automatic_launch_validation")

    def test_kingdoms_after_dark_manual_success_example_contains_key_stack(self):
        path = Path("docs/examples/compatibility_memory/kingdoms-after-dark-manual-success.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        mods = set(data["mods"])

        for expected in {"sodium", "lithium", "ferrite-core", "iris", "terralith", "when-dungeons-arise"}:
            self.assertIn(expected, mods)
