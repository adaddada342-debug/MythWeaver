import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.test_runtime_stabilization import HWG_AZURELIB_CRASH, IPN_KOTLIN_CRASH, RuntimeFacade, RuntimeStabilizationTests


class LauncherAutomationTests(unittest.IsolatedAsyncioTestCase):
    def selected(self, mods=None):
        return RuntimeStabilizationTests().selected(mods)

    def write_fake_instance(self, root: Path, *, fabric: bool = True, memory: int = 8192, minecraft: str = "1.20.1") -> Path:
        instance = root / "instance"
        instance.mkdir(parents=True, exist_ok=True)
        components = [{"uid": "net.minecraft", "version": minecraft}]
        if fabric:
            components.append({"uid": "net.fabricmc.fabric-loader", "version": "0.15.11"})
        (instance / "mmc-pack.json").write_text(json.dumps({"components": components}), encoding="utf-8")
        (instance / "instance.cfg").write_text(f"MaxMemAlloc={memory}\n", encoding="utf-8")
        mods = instance / ".minecraft" / "mods"
        mods.mkdir(parents=True, exist_ok=True)
        (mods / "sodium.jar").write_text("fake", encoding="utf-8")
        return instance

    def test_missing_launcher_detection_does_not_fake_success(self):
        from mythweaver.launcher.detection import detect_launcher

        report = detect_launcher("modrinth", env={"APPDATA": "", "LOCALAPPDATA": "", "USERPROFILE": ""}).detect_installation()

        self.assertIn(report.status, {"not_found", "manual_required"})
        self.assertFalse(report.executable_paths)

    def test_launcher_validation_detects_vanilla_missing_loader_and_low_memory(self):
        from mythweaver.launcher.validation import validate_launcher_instance

        root = Path.cwd() / "output" / "test-launcher-vanilla"
        instance = self.write_fake_instance(root, fabric=False, memory=2048)
        report = validate_launcher_instance(
            instance,
            launcher_name="prism",
            expected_minecraft_version="1.20.1",
            expected_loader="fabric",
            expected_loader_version=None,
            expected_memory_mb=8192,
        )

        kinds = {issue.kind for issue in report.issues}
        self.assertEqual(report.status, "failed")
        self.assertIn("vanilla_instance", kinds)
        self.assertIn("missing_loader", kinds)
        self.assertIn("memory_too_low", kinds)

    def test_valid_fake_fabric_instance_passes_validation(self):
        from mythweaver.launcher.validation import validate_launcher_instance

        root = Path.cwd() / "output" / "test-launcher-valid"
        instance = self.write_fake_instance(root, fabric=True, memory=8192)
        report = validate_launcher_instance(
            instance,
            launcher_name="prism",
            expected_minecraft_version="1.20.1",
            expected_loader="fabric",
            expected_loader_version=None,
            expected_memory_mb=8192,
        )

        self.assertEqual(report.status, "passed")
        self.assertEqual(report.loader, "fabric")
        self.assertEqual(report.memory_mb, 8192)

    def test_setup_launcher_manual_required_writes_reports_and_instructions(self):
        from mythweaver.cli.main import _fallback_main

        root = Path.cwd() / "output" / "test-setup-launcher"
        root.mkdir(parents=True, exist_ok=True)
        pack = root / "pack.mrpack"
        pack.write_text("fake mrpack", encoding="utf-8")

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = _fallback_main(
                [
                    "setup-launcher",
                    str(pack),
                    "--launcher",
                    "modrinth",
                    "--instance-name",
                    "Peacekeeper Worldbreaker",
                    "--minecraft-version",
                    "1.20.1",
                    "--loader",
                    "fabric",
                    "--memory-mb",
                    "8192",
                    "--output-dir",
                    str(root),
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["instance"]["status"], "manual_required")
        self.assertTrue((root / "launcher_instance_report.json").is_file())
        self.assertTrue((root / "launcher_validation_report.json").is_file())
        self.assertTrue((root / "launcher_import_instructions.md").is_file())

    def test_user_facing_launcher_commands_have_help(self):
        from mythweaver.cli.main import _fallback_main

        for command in ["setup-launcher", "launch-check", "autonomous-build"]:
            stdout = StringIO()
            with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
                _fallback_main([command, "--help"])

            self.assertEqual(raised.exception.code, 0)
            self.assertTrue(stdout.getvalue())

    def test_launch_check_new_cli_with_crash_report_fails_with_analysis(self):
        from mythweaver.cli.main import _fallback_main

        root = Path.cwd() / "output" / "test-launch-check-new-cli"
        instance = self.write_fake_instance(root)
        crash = root / "crash.txt"
        crash.write_text(IPN_KOTLIN_CRASH, encoding="utf-8")

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = _fallback_main(
                [
                    "launch-check",
                    "--launcher",
                    "modrinth",
                    "--instance-path",
                    str(instance),
                    "--crash-report",
                    str(crash),
                    "--output-dir",
                    str(root),
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["crash_analysis"]["crashing_mod_id"], "inventoryprofilesnext")
        self.assertTrue((root / "runtime_smoke_test_report.json").is_file())

    async def test_autonomous_build_manual_crash_removes_optional_hwg_and_writes_report(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-autonomous-build"
        concept = root / "concept.md"
        crash = root / "crash.txt"
        root.mkdir(parents=True, exist_ok=True)
        concept.write_text("# Peacekeeper Worldbreaker\n\nStable combat pack.", encoding="utf-8")
        crash.write_text(HWG_AZURELIB_CRASH, encoding="utf-8")

        report = await AgentModpackService(RuntimeFacade()).autonomous_build(
            concept,
            root,
            selected=self.selected(),
            launcher="modrinth",
            memory_mb=8192,
            max_attempts=2,
            no_launch=True,
            manual_crash_report=crash,
        )

        self.assertEqual(report.status, "needs_manual_review")
        self.assertTrue((root / "autonomous_build_report.json").is_file())
        self.assertTrue((root / "selected_mods.attempt-1.json").is_file())
        self.assertTrue(report.attempts[0].removed_mods)
        final_selected = json.loads(Path(report.final_selected_mods_path).read_text(encoding="utf-8"))
        self.assertNotIn("hwg", {entry.get("slug") for entry in final_selected["mods"]})
        self.assertLessEqual(len(report.attempts), 2)

    async def test_autonomous_build_does_not_remove_core_worldgen_automatically(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-autonomous-core"
        concept = root / "concept.md"
        crash = root / "crash.txt"
        root.mkdir(parents=True, exist_ok=True)
        concept.write_text("# Core Worldgen\n\nA worldgen-first pack.", encoding="utf-8")
        crash.write_text(
            "java.lang.RuntimeException: Could not execute entrypoint stage 'main' due to errors, provided by 'terralith'\n",
            encoding="utf-8",
        )
        selected = self.selected([{"slug": "terralith", "role": "theme", "reason_selected": "Core world identity"}])

        report = await AgentModpackService(RuntimeFacade()).autonomous_build(
            concept,
            root,
            selected=selected,
            launcher="modrinth",
            memory_mb=8192,
            max_attempts=1,
            no_launch=True,
            manual_crash_report=crash,
        )

        self.assertNotEqual(report.status, "stable")
        self.assertFalse(report.attempts[0].removed_mods)

    def test_agent_workflow_prompt_mentions_launcher_setup(self):
        from mythweaver.handoff import write_agent_workflow_prompt

        root = Path.cwd() / "output" / "test-launcher-workflow"
        concept = root / "concept.md"
        concept.parent.mkdir(parents=True, exist_ok=True)
        concept.write_text("# Launcher Ready\n\nMake it playable.", encoding="utf-8")
        report = write_agent_workflow_prompt(concept, concept.read_text(encoding="utf-8"), output_dir=root)
        text = Path(report.prompt_path).read_text(encoding="utf-8")

        self.assertIn("setup-launcher", text)
        self.assertIn("launch-check", text)
        self.assertIn("dry-run is not enough", text)
        self.assertIn("RAM and Fabric setup must be validated", text)

    def test_readme_mentions_autonomous_pack_creation(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("Autonomous pack creation", readme)
        self.assertIn("autonomous-build concepts/peacekeeper_worldbreaker.md --launcher modrinth --memory-mb 8192", readme)
