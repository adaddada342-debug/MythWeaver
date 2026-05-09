import json
import unittest
from pathlib import Path


SMOKE_OK = "\n".join(
    [
        "[MythWeaverSmokeTest] CLIENT_READY",
        "[MythWeaverSmokeTest] SERVER_STARTED",
        "[MythWeaverSmokeTest] PLAYER_JOINED_WORLD",
        "[MythWeaverSmokeTest] STABLE_60_SECONDS",
    ]
)


class EndToEndRuntimeContractTests(unittest.IsolatedAsyncioTestCase):
    def selected(self):
        from mythweaver.schemas.contracts import SelectedModList

        return SelectedModList.model_validate(
            {
                "name": "Runtime Contract Pack",
                "summary": "Fixture-only runtime contract pack.",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": [{"slug": "sodium", "role": "foundation", "reason_selected": "Performance"}],
            }
        )

    def write_fake_prism_instance(self, root: Path) -> Path:
        instance = root / "instance"
        (instance / ".minecraft" / "mods").mkdir(parents=True, exist_ok=True)
        (instance / ".minecraft" / "logs").mkdir(parents=True, exist_ok=True)
        (instance / ".minecraft" / "mods" / "sodium.jar").write_text("fixture mod", encoding="utf-8")
        (instance / "mmc-pack.json").write_text(
            json.dumps(
                {
                    "components": [
                        {"uid": "net.minecraft", "version": "1.20.1"},
                        {"uid": "net.fabricmc.fabric-loader", "version": "0.15.11"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        (instance / "instance.cfg").write_text("MaxMemAlloc=8192\n", encoding="utf-8")
        return instance

    async def test_fixture_runtime_contract_reaches_stable_only_after_smoke_proof(self):
        from mythweaver.launcher.runtime import run_launch_check
        from mythweaver.launcher.smoketest import inject_smoke_test_mod, remove_injected_smoke_test_mod
        from mythweaver.launcher.validation import validate_launcher_instance
        from mythweaver.launcher.validation_world import create_validation_world, remove_validation_world
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import (
            AgentPackReport,
            BuildArtifact,
            LauncherInstanceReport,
            LauncherValidationReport,
            RuntimeSmokeTestReport,
        )

        root = Path.cwd() / "output" / "test-end-to-end-runtime-contract"
        instance = self.write_fake_prism_instance(root)
        helper = root / "fixtures" / "mythweaver-smoketest.jar"
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text("fixture helper jar", encoding="utf-8")
        latest = instance / ".minecraft" / "logs" / "latest.log"
        latest.write_text(SMOKE_OK, encoding="utf-8")

        launcher_validation = validate_launcher_instance(
            instance,
            launcher_name="prism",
            expected_minecraft_version="1.20.1",
            expected_loader="fabric",
            expected_loader_version=None,
            expected_memory_mb=8192,
        )
        injection = inject_smoke_test_mod(instance, helper_mod_path=helper)
        world = create_validation_world(instance)
        runtime = run_launch_check(
            launcher="prism",
            instance_path=None,
            wait_seconds=60,
            output_dir=root,
            latest_log=latest,
            smoke_test_mod_injected=True,
        )
        remove_validation_world(world)
        remove_injected_smoke_test_mod(injection)

        self.assertEqual(launcher_validation.status, "passed")
        self.assertEqual(injection.status, "injected")
        self.assertTrue(world.removed_after_validation)
        self.assertEqual(runtime.status, "passed")
        self.assertTrue(runtime.runtime_proof_observed)
        self.assertEqual(runtime.stability_seconds_proven, 60)

        class FakeFacade:
            settings = None

        class ContractService(AgentModpackService):
            async def build_from_list(self, selected, output_dir, **kwargs):
                output_dir = Path(output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                return AgentPackReport(
                    run_id="fixture",
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
                return (
                    LauncherInstanceReport(
                        status="created",
                        launcher_name="prism",
                        instance_name="Runtime Contract Pack",
                        instance_path=str(instance),
                        generated_instance_path=str(instance),
                        prism_registered_instance_path=str(instance),
                        prism_instance_id="runtime-contract-pack",
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
                        summary="Fixture launcher validation passed.",
                    ),
                )

            async def launcher_launch_check(self, **kwargs):
                return RuntimeSmokeTestReport(
                    status="passed",
                    stage="complete",
                    summary="Fixture smoke proof passed.",
                    smoke_test_mod_injected=True,
                    smoke_test_markers_seen=["CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_60_SECONDS"],
                    required_markers_met=True,
                    stability_seconds_proven=60,
                    runtime_proof_observed=True,
                )

        concept = root / "concept.md"
        concept.write_text("# Runtime Contract Pack\n", encoding="utf-8")
        final = await ContractService(FakeFacade()).autonomous_build(
            concept,
            root / "autonomous",
            selected=self.selected(),
            sources=None,
            max_attempts=1,
        )

        self.assertEqual(final.status, "stable")
        self.assertTrue(final.runtime_proof_observed)
        self.assertEqual(final.final_status_reason, "runtime_smoke_test_passed")
        attempt = final.attempts[0]
        self.assertEqual(attempt.build_report_path is not None, True)
        self.assertEqual(attempt.launcher_validation_report.status, "passed")
        self.assertEqual(attempt.runtime_smoke_test_report.status, "passed")

    async def test_autonomous_contract_refuses_stable_without_smoke_markers(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import AgentPackReport, BuildArtifact, LauncherInstanceReport, LauncherValidationReport, RuntimeSmokeTestReport

        root = Path.cwd() / "output" / "test-end-to-end-runtime-contract-negative"
        instance = self.write_fake_prism_instance(root)

        class FakeFacade:
            settings = None

        class MissingProofService(AgentModpackService):
            async def build_from_list(self, selected, output_dir, **kwargs):
                return AgentPackReport(
                    run_id="fixture",
                    status="completed",
                    name=selected.name,
                    minecraft_version=selected.minecraft_version,
                    loader=selected.loader,
                    dependency_closure_passed=True,
                    generated_artifacts=[BuildArtifact(kind="prism-instance", path=str(instance))],
                    output_dir=str(output_dir),
                )

            async def setup_launcher(self, pack_artifact, output_dir, **kwargs):
                return (
                    LauncherInstanceReport(
                        status="created",
                        launcher_name="prism",
                        instance_name="Runtime Contract Pack",
                        instance_path=str(instance),
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
                        summary="Fixture launcher validation passed.",
                    ),
                )

            async def launcher_launch_check(self, **kwargs):
                return RuntimeSmokeTestReport(
                    status="manual_required",
                    stage="world_join",
                    summary="PLAYER_JOINED_WORLD without stability marker.",
                    smoke_test_markers_seen=["CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD"],
                    required_markers_met=False,
                    runtime_proof_observed=False,
                )

        concept = root / "concept.md"
        concept.write_text("# Runtime Contract Pack\n", encoding="utf-8")
        report = await MissingProofService(FakeFacade()).autonomous_build(
            concept,
            root / "autonomous",
            selected=self.selected(),
            sources=None,
            max_attempts=1,
        )

        self.assertNotEqual(report.status, "stable")
        self.assertEqual(report.final_status_reason, "runtime_proof_missing")
        self.assertFalse(report.runtime_proof_observed)

    def test_negative_fixture_logs_do_not_satisfy_runtime_contract(self):
        from mythweaver.launcher.runtime import _runtime_report_from_log, run_launch_check
        from mythweaver.launcher.smoketest import inject_smoke_test_mod

        root = Path.cwd() / "output" / "test-end-to-end-runtime-contract-log-negatives"
        root.mkdir(parents=True, exist_ok=True)
        cases = {
            "client_ready": "[MythWeaverSmokeTest] CLIENT_READY\n",
            "join_only": "[MythWeaverSmokeTest] PLAYER_JOINED_WORLD\n",
            "vanilla_join": "Started integrated server\nJoining world\n",
        }
        for name, text in cases.items():
            latest = root / f"{name}.log"
            latest.write_text(text, encoding="utf-8")
            report = run_launch_check(
                launcher="prism",
                instance_path=None,
                wait_seconds=60,
                output_dir=root,
                latest_log=latest,
                smoke_test_mod_injected=name != "vanilla_join",
            )
            self.assertNotEqual(report.status, "passed", name)
            self.assertFalse(report.required_markers_met, name)

        missing = inject_smoke_test_mod(root / "instance", helper_mod_path=root / "missing.jar")
        self.assertEqual(missing.status, "missing_helper")

        latest = root / "nonzero.log"
        latest.write_text(SMOKE_OK, encoding="utf-8")
        nonzero = _runtime_report_from_log(
            latest,
            wait_seconds=60,
            smoke_test_mod_injected=True,
            summary_if_missing="missing",
            process_exit_code=1,
        )
        self.assertEqual(nonzero.status, "failed")
