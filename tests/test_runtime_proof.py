import json
import os
import unittest
from unittest.mock import patch
from pathlib import Path


SMOKE_PASS_LOG = """
[12:00:00] [Render thread/INFO]: [MythWeaverSmokeTest] CLIENT_READY
[12:00:01] [Server thread/INFO]: [MythWeaverSmokeTest] SERVER_STARTED
[12:00:02] [Render thread/INFO]: [MythWeaverSmokeTest] PLAYER_JOINED_WORLD
[12:01:02] [Render thread/INFO]: [MythWeaverSmokeTest] STABLE_60_SECONDS
"""


class RuntimeProofTests(unittest.TestCase):
    def test_smoke_helper_locator_prefers_env_then_resources_then_tooling(self):
        from mythweaver.launcher.smoketest import locate_smoke_test_helper

        root = Path.cwd() / "output" / "test-smoke-locator"
        env_jar = root / "env.jar"
        resources_jar = root / "resources" / "mythweaver-smoketest.jar"
        tooling_jar = root / "tooling" / "mythweaver-smoketest" / "build" / "libs" / "mythweaver-smoketest-dev.jar"
        for path in (env_jar, resources_jar, tooling_jar):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fake", encoding="utf-8")

        with patch.dict(os.environ, {"MYTHWEAVER_SMOKETEST_MOD_PATH": str(env_jar)}):
            self.assertEqual(locate_smoke_test_helper(search_root=root), env_jar)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(locate_smoke_test_helper(search_root=root), resources_jar)
            resources_jar.unlink()
            self.assertEqual(locate_smoke_test_helper(search_root=root), tooling_jar)

    def test_smoke_helper_mod_project_contains_required_fabric_files_and_markers(self):
        project = Path.cwd() / "tooling" / "mythweaver-smoketest"
        expected = [
            project / "settings.gradle",
            project / "build.gradle",
            project / "src" / "main" / "resources" / "fabric.mod.json",
            project / "src" / "main" / "java" / "dev" / "mythweaver" / "smoketest" / "MythWeaverSmokeTest.java",
            project / "src" / "main" / "java" / "dev" / "mythweaver" / "smoketest" / "MythWeaverSmokeTestClient.java",
            project / "build_smoketest.py",
            project / "gradlew",
            project / "gradlew.bat",
            project / "gradle" / "wrapper" / "gradle-wrapper.properties",
            project / "gradle" / "wrapper" / "gradle-wrapper.jar",
        ]

        for path in expected:
            self.assertTrue(path.is_file(), f"missing {path}")

        combined = "\n".join(path.read_text(encoding="utf-8") for path in expected if path.suffix in {".json", ".java", ".gradle", ".py"})
        self.assertIn("mythweaver_smoketest", combined)
        self.assertIn("[MythWeaverSmokeTest]", combined)
        for marker in ["CLIENT_READY", "SERVER_STARTING", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_30_SECONDS", "STABLE_60_SECONDS", "STABLE_120_SECONDS"]:
            self.assertIn(marker, combined)

    def test_smoke_markers_parse_and_stable_60_passes(self):
        from mythweaver.launcher.runtime import run_launch_check

        root = Path.cwd() / "output" / "test-smoke-markers-pass"
        root.mkdir(parents=True, exist_ok=True)
        latest = root / "latest.log"
        latest.write_text(SMOKE_PASS_LOG, encoding="utf-8")

        report = run_launch_check(
            launcher="prism",
            instance_path=None,
            wait_seconds=60,
            output_dir=root,
            latest_log=latest,
            smoke_test_mod_injected=True,
        )

        self.assertEqual(report.status, "passed")
        self.assertTrue(report.required_markers_met)
        self.assertEqual(report.stability_seconds_proven, 60)
        self.assertIn("PLAYER_JOINED_WORLD", report.smoke_test_markers_seen)
        self.assertIn("STABLE_60_SECONDS", report.smoke_test_markers_seen)

    def test_world_join_without_stability_marker_does_not_pass(self):
        from mythweaver.launcher.runtime import run_launch_check

        root = Path.cwd() / "output" / "test-smoke-world-join-only"
        root.mkdir(parents=True, exist_ok=True)
        latest = root / "latest.log"
        latest.write_text(
            "[MythWeaverSmokeTest] CLIENT_READY\n"
            "[MythWeaverSmokeTest] SERVER_STARTED\n"
            "[MythWeaverSmokeTest] PLAYER_JOINED_WORLD\n",
            encoding="utf-8",
        )

        report = run_launch_check(
            launcher="prism",
            instance_path=None,
            wait_seconds=120,
            output_dir=root,
            latest_log=latest,
            smoke_test_mod_injected=True,
        )

        self.assertNotEqual(report.status, "passed")
        self.assertFalse(report.required_markers_met)
        self.assertEqual(report.stability_seconds_proven, 0)

    def test_client_ready_alone_and_stable_without_join_do_not_pass(self):
        from mythweaver.launcher.runtime import run_launch_check

        root = Path.cwd() / "output" / "test-smoke-marker-negative-cases"
        root.mkdir(parents=True, exist_ok=True)
        client_ready = root / "client_ready.log"
        stable_without_join = root / "stable_without_join.log"
        client_ready.write_text("[MythWeaverSmokeTest] CLIENT_READY\n", encoding="utf-8")
        stable_without_join.write_text(
            "[MythWeaverSmokeTest] CLIENT_READY\n[MythWeaverSmokeTest] SERVER_STARTED\n[MythWeaverSmokeTest] STABLE_60_SECONDS\n",
            encoding="utf-8",
        )

        for latest in (client_ready, stable_without_join):
            report = run_launch_check(
                launcher="prism",
                instance_path=None,
                wait_seconds=60,
                output_dir=root,
                latest_log=latest,
                smoke_test_mod_injected=True,
            )
            self.assertNotEqual(report.status, "passed")
            self.assertFalse(report.required_markers_met)

    def test_crash_or_nonzero_exit_after_join_fails(self):
        from mythweaver.launcher.runtime import _runtime_report_from_log

        root = Path.cwd() / "output" / "test-smoke-crash-nonzero"
        root.mkdir(parents=True, exist_ok=True)
        latest = root / "latest.log"
        latest.write_text(
            "[MythWeaverSmokeTest] CLIENT_READY\n"
            "[MythWeaverSmokeTest] SERVER_STARTED\n"
            "[MythWeaverSmokeTest] PLAYER_JOINED_WORLD\n"
            "[MythWeaverSmokeTest] STABLE_60_SECONDS\n"
            "Reported exception\n",
            encoding="utf-8",
        )
        clean_latest = root / "clean_latest.log"
        clean_latest.write_text(
            "[MythWeaverSmokeTest] CLIENT_READY\n"
            "[MythWeaverSmokeTest] SERVER_STARTED\n"
            "[MythWeaverSmokeTest] PLAYER_JOINED_WORLD\n"
            "[MythWeaverSmokeTest] STABLE_60_SECONDS\n",
            encoding="utf-8",
        )

        crashed = _runtime_report_from_log(latest, wait_seconds=60, smoke_test_mod_injected=True, summary_if_missing="missing")
        nonzero = _runtime_report_from_log(
            clean_latest,
            wait_seconds=60,
            smoke_test_mod_injected=True,
            summary_if_missing="missing",
            process_exit_code=1,
        )

        self.assertEqual(crashed.status, "failed")
        self.assertEqual(nonzero.status, "failed")

    def test_marker_parser_detects_all_required_markers(self):
        from mythweaver.launcher.runtime import parse_smoke_test_markers, stability_seconds_from_markers

        root = Path.cwd() / "output" / "test-smoke-marker-parser-all"
        root.mkdir(parents=True, exist_ok=True)
        latest = root / "latest.log"
        latest.write_text(
            "\n".join(f"[12:00:00] [Server thread/INFO]: [MythWeaverSmokeTest] {marker}" for marker in [
                "CLIENT_READY",
                "SERVER_STARTING",
                "SERVER_STARTED",
                "PLAYER_JOINED_WORLD",
                "STABLE_30_SECONDS",
                "STABLE_60_SECONDS",
                "STABLE_120_SECONDS",
            ]),
            encoding="utf-8",
        )

        markers, timestamps = parse_smoke_test_markers(latest)

        self.assertEqual(stability_seconds_from_markers(markers), 120)
        self.assertIn("STABLE_120_SECONDS", markers)
        self.assertIn("PLAYER_JOINED_WORLD", timestamps)

    def test_vanilla_world_join_alone_is_manual_required(self):
        from mythweaver.launcher.runtime import run_launch_check

        root = Path.cwd() / "output" / "test-vanilla-world-join-only"
        root.mkdir(parents=True, exist_ok=True)
        latest = root / "latest.log"
        latest.write_text("Started integrated server\nJoining world\n", encoding="utf-8")

        report = run_launch_check(
            launcher="prism",
            instance_path=None,
            wait_seconds=120,
            output_dir=root,
            latest_log=latest,
        )

        self.assertEqual(report.status, "manual_required")
        self.assertFalse(report.runtime_proof_observed)
        self.assertIn("world_join", report.detected_markers)

    def test_smoke_helper_injection_copies_and_removes_validation_jar(self):
        from mythweaver.launcher.smoketest import inject_smoke_test_mod, remove_injected_smoke_test_mod

        root = Path.cwd() / "output" / "test-smoke-injection"
        helper = root / "resources" / "mythweaver-smoketest.jar"
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text("fake jar", encoding="utf-8")
        instance = root / "instance"

        report = inject_smoke_test_mod(instance, helper_mod_path=helper)

        self.assertEqual(report.status, "injected")
        self.assertTrue(Path(report.injected_file_path).is_file())
        self.assertTrue(report.final_export_excluded)

        removed = remove_injected_smoke_test_mod(report)
        self.assertTrue(removed.removed_after_validation)
        self.assertFalse(Path(report.injected_file_path).exists())

    def test_missing_smoke_helper_reports_missing_not_success(self):
        from mythweaver.launcher.smoketest import inject_smoke_test_mod

        root = Path.cwd() / "output" / "test-smoke-helper-missing"
        report = inject_smoke_test_mod(root / "instance", helper_mod_path=root / "missing.jar")

        self.assertEqual(report.status, "missing_helper")
        self.assertFalse(report.helper_mod_path)

    def test_validation_world_create_and_cleanup_do_not_prove_runtime(self):
        from mythweaver.launcher.runtime import run_launch_check
        from mythweaver.launcher.validation_world import create_validation_world, remove_validation_world

        root = Path.cwd() / "output" / "test-validation-world"
        instance = root / "instance"

        created = create_validation_world(instance)
        self.assertEqual(created.status, "created")
        self.assertTrue(Path(created.world_path).is_dir())

        report = run_launch_check(
            launcher="prism",
            instance_path=None,
            wait_seconds=120,
            output_dir=root,
            latest_log=instance / ".minecraft" / "logs" / "latest.log",
        )
        self.assertNotEqual(report.status, "passed")

        removed = remove_validation_world(created)
        self.assertTrue(removed.removed_after_validation)
        self.assertFalse(Path(created.world_path).exists())

    def test_prism_unregistered_instance_is_manual_required(self):
        from mythweaver.launcher.prism import PrismLauncherAdapter

        root = Path.cwd() / "output" / "test-prism-unregistered"
        executable = root / "PrismLauncher.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text("", encoding="utf-8")
        instance = root / "generated" / "pack"
        instance.mkdir(parents=True, exist_ok=True)

        report = PrismLauncherAdapter(
            env={
                "MYTHWEAVER_PRISM_EXECUTABLE_PATH": str(executable),
                "MYTHWEAVER_PRISM_INSTANCES_PATH": str(root / "PrismLauncher" / "instances"),
            }
        ).launch_instance(instance, wait_seconds=1, output_dir=root)

        self.assertEqual(report.status, "manual_required")
        self.assertIn("not registered", report.summary)

    def test_prism_keep_validation_world_preserves_registered_world_on_launch_failure(self):
        from mythweaver.launcher.prism import PrismLauncherAdapter
        from mythweaver.launcher.validation_world import create_validation_world

        root = Path.cwd() / "output" / "test-prism-keep-validation-world"
        instances = root / "PrismLauncher" / "instances"
        instance = instances / "pack"
        instance.mkdir(parents=True, exist_ok=True)
        executable = root / "PrismLauncher.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text("", encoding="utf-8")
        world = create_validation_world(instance)

        PrismLauncherAdapter(
            env={
                "MYTHWEAVER_PRISM_EXECUTABLE_PATH": str(executable),
                "MYTHWEAVER_PRISM_INSTANCES_PATH": str(instances),
            }
        ).launch_instance(instance, wait_seconds=1, output_dir=root, validation_world=True, keep_validation_world=True)

        self.assertTrue(Path(world.world_path).exists())

    def test_registered_prism_instance_records_exact_launch_command_in_evidence(self):
        from mythweaver.launcher.prism import PrismLauncherAdapter

        root = Path.cwd() / "output" / "test-prism-mocked-launch-command"
        instances = root / "PrismLauncher" / "instances"
        instance = instances / "proof-pack"
        log_dir = instance / ".minecraft" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        latest = log_dir / "latest.log"
        latest.write_text(
            "[MythWeaverSmokeTest] CLIENT_READY\n"
            "[MythWeaverSmokeTest] SERVER_STARTED\n"
            "[MythWeaverSmokeTest] PLAYER_JOINED_WORLD\n"
            "[MythWeaverSmokeTest] STABLE_60_SECONDS\n",
            encoding="utf-8",
        )
        executable = root / "PrismLauncher.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text("", encoding="utf-8")

        class FakeProcess:
            def poll(self):
                return None

            def terminate(self):
                return None

            def wait(self, timeout=None):
                return 0

            def kill(self):
                return None

        with patch("mythweaver.launcher.prism.subprocess.Popen", return_value=FakeProcess()) as popen, patch("mythweaver.launcher.prism.time.sleep", return_value=None):
            report = PrismLauncherAdapter(
                env={
                    "MYTHWEAVER_PRISM_EXECUTABLE_PATH": str(executable),
                    "MYTHWEAVER_PRISM_INSTANCES_PATH": str(instances),
                }
            ).launch_instance(instance, wait_seconds=1, output_dir=root, smoke_test_mod_injected=True)

        evidence = json.loads((root / "runtime_evidence_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report.status, "passed")
        self.assertEqual(evidence["command"], [str(executable), "--launch", "proof-pack"])
        self.assertEqual(evidence["prism_instance_id"], "proof-pack")
        self.assertEqual(evidence["prism_registered_instance_path"], str(instance))
        self.assertEqual(popen.call_args.args[0], [str(executable), "--launch", "proof-pack"])

    def test_generated_prism_instance_with_metadata_is_registered_before_launch(self):
        from mythweaver.launcher.prism import PrismLauncherAdapter

        root = Path.cwd() / "output" / "test-prism-register-generated"
        instances = root / "PrismLauncher" / "instances"
        instances.mkdir(parents=True, exist_ok=True)
        generated = root / "generated" / "proof-pack"
        (generated / ".minecraft" / "logs").mkdir(parents=True, exist_ok=True)
        (generated / "mmc-pack.json").write_text(json.dumps({"components": []}), encoding="utf-8")
        (generated / "instance.cfg").write_text("MaxMemAlloc=8192\n", encoding="utf-8")
        (generated / ".minecraft" / "logs" / "latest.log").write_text(
            "[MythWeaverSmokeTest] CLIENT_READY\n"
            "[MythWeaverSmokeTest] SERVER_STARTED\n"
            "[MythWeaverSmokeTest] PLAYER_JOINED_WORLD\n"
            "[MythWeaverSmokeTest] STABLE_60_SECONDS\n",
            encoding="utf-8",
        )
        executable = root / "PrismLauncher.exe"
        executable.write_text("", encoding="utf-8")

        class FakeProcess:
            def poll(self):
                return None

            def terminate(self):
                return None

            def wait(self, timeout=None):
                return 0

            def kill(self):
                return None

        with patch("mythweaver.launcher.prism.subprocess.Popen", return_value=FakeProcess()), patch("mythweaver.launcher.prism.time.sleep", return_value=None):
            report = PrismLauncherAdapter(
                env={
                    "MYTHWEAVER_PRISM_EXECUTABLE_PATH": str(executable),
                    "MYTHWEAVER_PRISM_INSTANCES_PATH": str(instances),
                }
            ).launch_instance(generated, wait_seconds=1, output_dir=root, smoke_test_mod_injected=True)

        self.assertEqual(report.status, "passed")
        self.assertTrue((instances / "proof-pack" / "instance.cfg").is_file())

    def test_runtime_evidence_json_includes_smoke_fields(self):
        from mythweaver.launcher.runtime import run_launch_check, write_runtime_smoke_report

        root = Path.cwd() / "output" / "test-runtime-evidence-smoke-fields"
        root.mkdir(parents=True, exist_ok=True)
        latest = root / "latest.log"
        latest.write_text(SMOKE_PASS_LOG, encoding="utf-8")

        report = run_launch_check(
            launcher="prism",
            instance_path=None,
            wait_seconds=120,
            output_dir=root,
            latest_log=latest,
            smoke_test_mod_injected=True,
        )
        write_runtime_smoke_report(report, root)
        payload = json.loads((root / "runtime_smoke_test_report.json").read_text(encoding="utf-8"))

        self.assertTrue(payload["runtime_proof_observed"])
        self.assertTrue(payload["final_export_excluded_smoketest_mod"])

    def test_cli_help_mentions_smoke_test_options(self):
        from contextlib import redirect_stdout
        from io import StringIO

        from mythweaver.cli.main import _fallback_main

        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            _fallback_main(["launch-check", "--help"])

        self.assertEqual(raised.exception.code, 0)
        text = stdout.getvalue()
        self.assertIn("--inject-smoke-test-mod", text)
        self.assertIn("--validation-world", text)

        autonomous = StringIO()
        with redirect_stdout(autonomous), self.assertRaises(SystemExit) as autonomous_raised:
            _fallback_main(["autonomous-build", "--help"])
        self.assertEqual(autonomous_raised.exception.code, 0)
        self.assertIn("--keep-validation-world", autonomous.getvalue())
        self.assertIn("--no-validation-world", autonomous.getvalue())

    def test_agent_workflow_prompt_requires_runtime_proof_markers(self):
        from mythweaver.handoff import write_agent_workflow_prompt

        root = Path.cwd() / "output" / "test-runtime-proof-prompt"
        concept = root / "concept.md"
        concept.parent.mkdir(parents=True, exist_ok=True)
        concept.write_text("# Proof Pack\n\nMake it genuinely playable.", encoding="utf-8")

        report = write_agent_workflow_prompt(concept, concept.read_text(encoding="utf-8"), output_dir=root)
        text = Path(report.prompt_path).read_text(encoding="utf-8")

        self.assertIn("PLAYER_JOINED_WORLD plus STABLE_60_SECONDS", text)
        self.assertIn("World join alone is not enough", text)
        self.assertIn("--inject-smoke-test-mod", text)


class AutonomousRuntimeProofTests(unittest.IsolatedAsyncioTestCase):
    def selected(self):
        from mythweaver.schemas.contracts import SelectedModList

        return SelectedModList.model_validate(
            {
                "name": "Proof Pack",
                "summary": "Runtime proof test pack.",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": [{"slug": "sodium", "role": "foundation", "reason_selected": "Performance"}],
            }
        )

    async def test_autonomous_build_cannot_return_stable_without_runtime_proof(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import (
            AgentPackReport,
            BuildArtifact,
            LauncherInstanceReport,
            LauncherValidationReport,
            RuntimeSmokeTestReport,
        )

        class FakeFacade:
            settings = None

        class FakeService(AgentModpackService):
            async def build_from_list(self, selected, output_dir, **kwargs):
                output_dir = Path(output_dir)
                instance = output_dir / "instances" / "proof-pack"
                instance.mkdir(parents=True, exist_ok=True)
                return AgentPackReport(
                    run_id="fake",
                    status="completed",
                    name=selected.name,
                    summary=selected.summary,
                    minecraft_version=selected.minecraft_version,
                    loader=selected.loader,
                    dependency_closure_passed=True,
                    generated_artifacts=[BuildArtifact(kind="prism-instance", path=str(instance))],
                    output_dir=str(output_dir),
                )

            async def setup_launcher(self, pack_artifact, output_dir, **kwargs):
                instance = Path(output_dir) / "instances" / "proof-pack"
                return (
                    LauncherInstanceReport(
                        status="created",
                        launcher_name="prism",
                        instance_name="Proof Pack",
                        instance_path=str(instance),
                        generated_instance_path=str(instance),
                        prism_registered_instance_path=str(instance),
                        prism_instance_id="proof-pack",
                        registered_with_prism=True,
                        pack_artifact_path=str(pack_artifact),
                        minecraft_version="1.20.1",
                        loader="fabric",
                        memory_mb=8192,
                    ),
                    LauncherValidationReport(
                        status="passed",
                        launcher_name="prism",
                        instance_path=str(instance),
                        minecraft_version="1.20.1",
                        loader="fabric",
                        memory_mb=8192,
                        summary="fake pass",
                    ),
                )

            async def launcher_launch_check(self, **kwargs):
                return RuntimeSmokeTestReport(
                    status="passed",
                    stage="complete",
                    summary="legacy world join pass without MythWeaver markers",
                    detected_markers=["world_join"],
                    runtime_proof_observed=False,
                    required_markers_met=False,
                )

        root = Path.cwd() / "output" / "test-autonomous-no-proof"
        root.mkdir(parents=True, exist_ok=True)
        concept = root / "concept.md"
        concept.write_text("# Proof Pack\n", encoding="utf-8")

        report = await FakeService(FakeFacade()).autonomous_build(
            concept,
            root,
            selected=self.selected(),
            sources=None,
            max_attempts=1,
        )

        self.assertNotEqual(report.status, "stable")
        self.assertEqual(report.final_status_reason, "runtime_proof_missing")
        self.assertFalse(report.runtime_proof_observed)

    async def test_autonomous_build_can_return_stable_with_runtime_proof(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import (
            AgentPackReport,
            BuildArtifact,
            LauncherInstanceReport,
            LauncherValidationReport,
            RuntimeSmokeTestReport,
        )

        class FakeFacade:
            settings = None

        class FakeService(AgentModpackService):
            async def build_from_list(self, selected, output_dir, **kwargs):
                output_dir = Path(output_dir)
                instance = output_dir / "instances" / "proof-pack"
                instance.mkdir(parents=True, exist_ok=True)
                return AgentPackReport(
                    run_id="fake",
                    status="completed",
                    name=selected.name,
                    summary=selected.summary,
                    minecraft_version=selected.minecraft_version,
                    loader=selected.loader,
                    dependency_closure_passed=True,
                    generated_artifacts=[BuildArtifact(kind="prism-instance", path=str(instance))],
                    output_dir=str(output_dir),
                )

            async def setup_launcher(self, pack_artifact, output_dir, **kwargs):
                instance = Path(output_dir) / "instances" / "proof-pack"
                return (
                    LauncherInstanceReport(
                        status="created",
                        launcher_name="prism",
                        instance_name="Proof Pack",
                        instance_path=str(instance),
                        generated_instance_path=str(instance),
                        prism_registered_instance_path=str(instance),
                        prism_instance_id="proof-pack",
                        registered_with_prism=True,
                        pack_artifact_path=str(pack_artifact),
                        minecraft_version="1.20.1",
                        loader="fabric",
                        memory_mb=8192,
                    ),
                    LauncherValidationReport(
                        status="passed",
                        launcher_name="prism",
                        instance_path=str(instance),
                        minecraft_version="1.20.1",
                        loader="fabric",
                        memory_mb=8192,
                        summary="fake pass",
                    ),
                )

            async def launcher_launch_check(self, **kwargs):
                return RuntimeSmokeTestReport(
                    status="passed",
                    stage="complete",
                    summary="smoke pass",
                    smoke_test_mod_injected=True,
                    smoke_test_markers_seen=["CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_60_SECONDS"],
                    required_markers_met=True,
                    stability_seconds_proven=60,
                    runtime_proof_observed=True,
                )

        root = Path.cwd() / "output" / "test-autonomous-with-proof"
        root.mkdir(parents=True, exist_ok=True)
        concept = root / "concept.md"
        concept.write_text("# Proof Pack\n", encoding="utf-8")

        report = await FakeService(FakeFacade()).autonomous_build(
            concept,
            root,
            selected=self.selected(),
            sources=None,
            max_attempts=1,
        )

        self.assertEqual(report.status, "stable")
        self.assertTrue(report.runtime_proof_observed)
        self.assertEqual(report.stability_seconds_proven, 60)
