import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


class AutopilotCliTests(unittest.TestCase):
    def test_cli_json_emits_valid_autopilot_report(self):
        from mythweaver.autopilot.contracts import AutopilotReport
        from mythweaver.cli.main import _fallback_main
        from mythweaver.runtime.contracts import RuntimeProof
        from mythweaver.schemas.contracts import SelectedModList

        root = Path(".test-output") / "autopilot-cli"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(name="CLI Pack", minecraft_version="1.20.1", loader="fabric", mods=[{"slug": "a"}]).model_dump_json(),
            encoding="utf-8",
        )
        fake_report = AutopilotReport(
            status="verified_playable",
            final_minecraft_version="1.20.1",
            final_loader="fabric",
            final_loader_version="0.15.11",
            attempts=[],
            final_instance_path=str(root / "runtime"),
            final_export_path=None,
            summary="Verified",
            warnings=[],
            final_proof=RuntimeProof(
                proof_level="stable_60",
                runtime_proof_observed=True,
                smoke_test_mod_used=True,
                smoke_test_markers_seen=["CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_60_SECONDS"],
                required_markers_met=True,
                stability_seconds_proven=60,
                evidence_path=str(root / "runtime_evidence.txt"),
            ),
        )

        async def fake_run(request):
            return fake_report

        stdout = StringIO()
        with patch("mythweaver.cli.main.run_autopilot", fake_run), redirect_stdout(stdout):
            code = _fallback_main(
                [
                    "autopilot",
                    str(selected_path),
                    "--json",
                    "--output-root",
                    str(root),
                    "--smoke-test-helper-path",
                    str(root / "fake-helper.jar"),
                    "--minimum-stability-seconds",
                    "60",
                ]
            )

        self.assertEqual(code, 0)
        parsed = json.loads(stdout.getvalue())
        self.assertEqual(parsed["status"], "verified_playable")
        self.assertEqual(parsed["final_proof"]["proof_level"], "stable_60")
        AutopilotReport.model_validate(parsed)

    def test_cli_human_output_includes_proof_diagnosis_action_and_report_path(self):
        from mythweaver.autopilot.contracts import AutopilotAppliedAction, AutopilotAttempt, AutopilotReport
        from mythweaver.cli.main import _fallback_main
        from mythweaver.runtime.contracts import RuntimeAction, RuntimeDiagnosis, RuntimeProof
        from mythweaver.schemas.contracts import SelectedModList

        root = Path(".test-output") / "autopilot-cli-human"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(name="CLI Human", minecraft_version="1.20.1", loader="fabric", mods=[]).model_dump_json(),
            encoding="utf-8",
        )
        action = RuntimeAction(action="add_mod", safety="safe", reason="Missing Fabric API", query="fabric-api")
        fake_report = AutopilotReport(
            status="blocked",
            final_minecraft_version="1.20.1",
            final_loader="fabric",
            final_loader_version=None,
            attempts=[
                AutopilotAttempt(
                    attempt_number=1,
                    minecraft_version="1.20.1",
                    loader="fabric",
                    loader_version=None,
                    build_status="resolved",
                    runtime_status="failed",
                    issues=[],
                    actions_planned=[action],
                    actions_applied=[AutopilotAppliedAction(action=action, status="blocked", reason="preflight failed")],
                    blocked_reasons=["preflight failed"],
                    instance_path=None,
                    diagnoses=[
                        RuntimeDiagnosis(
                            kind="missing_fabric_api",
                            confidence="high",
                            summary="Fabric API missing",
                            evidence=["requires mod fabric-api"],
                        )
                    ],
                )
            ],
            final_instance_path=None,
            final_export_path=None,
            summary="Blocked",
            warnings=[],
            final_proof=RuntimeProof(proof_level="client_initialized", stability_seconds_proven=0),
            report_paths={"json": str(root / "autopilot_report.json"), "markdown": str(root / "autopilot_report.md")},
        )

        async def fake_run(request):
            return fake_report

        stdout = StringIO()
        with patch("mythweaver.cli.main.run_autopilot", fake_run), redirect_stdout(stdout):
            code = _fallback_main(["autopilot", str(selected_path), "--output-root", str(root)])

        output = stdout.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED", output)
        self.assertIn("Proof client_initialized", output)
        self.assertIn("Diagnosis: missing_fabric_api", output)
        self.assertIn("Applied: blocked add_mod fabric-api", output)
        self.assertIn("Report:", output)

    def test_exit_code_for_autopilot_report_maps_agent_statuses(self):
        from mythweaver.autopilot.contracts import AutopilotBlocker, AutopilotReport
        from mythweaver.cli.main import exit_code_for_autopilot_report

        def report(status, blockers=None):
            return AutopilotReport(
                status=status,
                final_minecraft_version=None,
                final_loader=None,
                final_loader_version=None,
                attempts=[],
                final_instance_path=None,
                final_export_path=None,
                summary=status,
                warnings=[],
                blockers=blockers or [],
            )

        self.assertEqual(exit_code_for_autopilot_report(report("verified_playable")), 0)
        self.assertEqual(exit_code_for_autopilot_report(report("blocked")), 1)
        self.assertEqual(exit_code_for_autopilot_report(report("max_attempts_reached")), 2)
        self.assertEqual(exit_code_for_autopilot_report(report("failed")), 2)
        self.assertEqual(
            exit_code_for_autopilot_report(
                report(
                    "failed",
                    [
                        AutopilotBlocker(
                            kind="invalid_request",
                            message="bad",
                            severity="fatal",
                            agent_can_retry=True,
                            user_action_required=True,
                        )
                    ],
                )
            ),
            3,
        )


if __name__ == "__main__":
    unittest.main()
