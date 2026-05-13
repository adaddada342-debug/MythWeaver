import unittest


class AutopilotContractTests(unittest.TestCase):
    def test_request_defaults_and_attempt_records_runtime_issues(self):
        from mythweaver.autopilot.contracts import AutopilotAttempt, AutopilotReport, AutopilotRequest
        from mythweaver.runtime.contracts import RuntimeIssue

        request = AutopilotRequest(selected_mods_path="selected_mods.json", sources=["modrinth", "curseforge"])

        self.assertEqual(request.target_export, "local_instance")
        self.assertEqual(request.max_attempts, 5)
        self.assertTrue(request.allow_target_switch)

        issue = RuntimeIssue(
            kind="timeout",
            severity="fatal",
            confidence=0.8,
            message="Timed out",
            evidence=["timeout"],
        )
        attempt = AutopilotAttempt(
            attempt_number=1,
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version=None,
            build_status="resolved",
            runtime_status="failed",
            issues=[issue],
            actions_planned=[],
            actions_applied=[],
            blocked_reasons=[],
            instance_path=None,
        )
        report = AutopilotReport(
            status="blocked",
            final_minecraft_version=None,
            final_loader=None,
            final_loader_version=None,
            attempts=[attempt],
            final_instance_path=None,
            final_export_path=None,
            summary="Blocked by timeout",
            warnings=[],
        )

        self.assertIn("blocked", report.model_dump_json())


if __name__ == "__main__":
    unittest.main()
