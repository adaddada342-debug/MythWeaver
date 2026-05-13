import unittest
from pathlib import Path


class AutopilotReportPathTests(unittest.TestCase):
    def test_write_autopilot_report_populates_report_paths_and_human_diagnostics(self):
        from mythweaver.autopilot.contracts import AutopilotAttempt, AutopilotReport
        from mythweaver.autopilot.report import write_autopilot_report
        from mythweaver.runtime.contracts import RuntimeDiagnosis, RuntimeProof

        root = Path(".test-output") / "autopilot-report-paths"
        report = AutopilotReport(
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
                    actions_planned=[],
                    actions_applied=[],
                    blocked_reasons=["no safe repair"],
                    instance_path=None,
                    proof=RuntimeProof(proof_level="client_initialized"),
                    diagnoses=[
                        RuntimeDiagnosis(
                            kind="unknown_launch_failure",
                            confidence="low",
                            summary="Unknown failure",
                            evidence=["boom"],
                        )
                    ],
                )
            ],
            final_instance_path=None,
            final_export_path=None,
            summary="Blocked",
            warnings=[],
            final_proof=RuntimeProof(proof_level="client_initialized"),
        )

        write_autopilot_report(report, root)

        self.assertTrue((root / "autopilot_report.json").is_file())
        self.assertTrue((root / "autopilot_report.md").is_file())
        self.assertEqual(report.report_paths["json"], str(root / "autopilot_report.json"))
        human = (root / "autopilot_report.md").read_text(encoding="utf-8")
        self.assertIn("unknown_launch_failure", human)
        self.assertIn("client_initialized", human)


if __name__ == "__main__":
    unittest.main()
