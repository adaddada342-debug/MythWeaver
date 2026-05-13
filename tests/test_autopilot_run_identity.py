import json
import unittest
from pathlib import Path
from unittest.mock import patch


class AutopilotRunIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_id_artifacts_and_original_selection_are_preserved(self):
        from mythweaver.autopilot.contracts import AutopilotRequest, AutopilotReport
        from mythweaver.autopilot.loop import run_autopilot
        from mythweaver.runtime.contracts import RuntimeLaunchReport, RuntimeProof
        from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport

        root = Path(".test-output") / "autopilot-run-identity"
        root.mkdir(parents=True, exist_ok=True)
        selected = SelectedModList(name="Run Pack", minecraft_version="1.20.1", loader="fabric", mods=[])
        selected_path = root / "selected_mods.json"
        selected_text = selected.model_dump_json()
        selected_path.write_text(selected_text, encoding="utf-8")

        async def fake_resolve(selected_mods, **kwargs):
            return SourceResolveReport(
                status="resolved",
                minecraft_version=kwargs["minecraft_version"],
                loader=kwargs["loader"],
                selected_files=[],
                export_supported=True,
                dependency_closure_passed=True,
            )

        def fake_runtime(request):
            return RuntimeLaunchReport(
                status="passed",
                stage="monitor",
                instance_path=str(root / "runtime"),
                minecraft_version=request.minecraft_version,
                loader=request.loader,
                loader_version=request.loader_version,
                java_path=request.java_path,
                command_preview=[],
                exit_code=0,
                success_signal="MythWeaver smoke-test proof: stable_60",
                issues=[],
                recommended_next_actions=[],
                logs_scanned=[],
                warnings=[],
                proof=RuntimeProof(
                    proof_level="stable_60",
                    runtime_proof_observed=True,
                    smoke_test_mod_used=True,
                    smoke_test_markers_seen=["CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_60_SECONDS"],
                    required_markers_met=True,
                    stability_seconds_proven=60,
                    evidence_path=str(root / "evidence.txt"),
                ),
            )

        with (
            patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", fake_resolve),
            patch("mythweaver.autopilot.loop.run_runtime_validation", fake_runtime),
        ):
            report = await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    output_root=str(root),
                    run_id="unsafe run/id?",
                    minecraft_version="1.20.1",
                    loader="fabric",
                    sources=["local"],
                )
            )

        self.assertEqual(report.run_id, "unsafe_run_id")
        run_dir = root / "runs" / "unsafe_run_id"
        self.assertEqual(report.run_dir, str(run_dir))
        self.assertTrue((run_dir / "request.json").is_file())
        self.assertTrue((run_dir / "autopilot_report.json").is_file())
        self.assertTrue((run_dir / "autopilot_report.md").is_file())
        self.assertTrue((run_dir / "timeline.jsonl").is_file())
        self.assertTrue((run_dir / "working_selection.initial.json").is_file())
        self.assertTrue((run_dir / "working_selection.latest.json").is_file())
        self.assertTrue((run_dir / "target_state.json").is_file())
        self.assertTrue((run_dir / "memory.json").is_file())
        self.assertEqual(selected_path.read_text(encoding="utf-8"), selected_text)
        parsed_report = AutopilotReport.model_validate_json((run_dir / "autopilot_report.json").read_text(encoding="utf-8"))
        self.assertEqual(parsed_report.run_id, "unsafe_run_id")
        events = [json.loads(line) for line in (run_dir / "timeline.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(all(event["run_id"] == "unsafe_run_id" for event in events))
        self.assertIn("run_started", {event["type"] for event in events})
        self.assertIn("target_selected", {event["type"] for event in events})
        self.assertIn("runtime_validation_started", {event["type"] for event in events})
        self.assertIn("runtime_validation_completed", {event["type"] for event in events})
        self.assertIn("run_completed", {event["type"] for event in events})

    async def test_run_id_generated_when_omitted(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.loop import run_autopilot
        from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport

        root = Path(".test-output") / "autopilot-run-generated"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(name="Generated Run", minecraft_version="1.20.1", loader="forge", mods=[]).model_dump_json(),
            encoding="utf-8",
        )

        async def fake_resolve(selected_mods, **kwargs):
            return SourceResolveReport(
                status="failed",
                minecraft_version=kwargs["minecraft_version"],
                loader=kwargs["loader"],
                export_supported=False,
                export_blockers=["blocked for test"],
            )

        with patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", fake_resolve):
            report = await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    output_root=str(root),
                    minecraft_version="1.20.1",
                    loader="forge",
                    sources=["local"],
                    max_attempts=1,
                )
            )

        self.assertRegex(report.run_id, r"^mw_\d{8}_\d{6}_[0-9a-f]{8}$")
        self.assertTrue((root / "runs" / report.run_id / "request.json").is_file())


if __name__ == "__main__":
    unittest.main()
