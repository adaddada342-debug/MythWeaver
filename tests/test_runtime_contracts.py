import unittest


class RuntimeContractTests(unittest.TestCase):
    def test_launch_request_defaults_and_report_json(self):
        from mythweaver.runtime.contracts import RuntimeIssue, RuntimeLaunchReport, RuntimeLaunchRequest, RuntimeProof

        request = RuntimeLaunchRequest(
            instance_name="Pack",
            minecraft_version="1.20.1",
            loader="fabric",
            mod_files=["C:/mods/a.jar"],
        )

        self.assertEqual(request.memory_mb, 4096)
        self.assertEqual(request.timeout_seconds, 180)
        self.assertEqual(request.offline_username, "MythWeaver")
        self.assertTrue(request.inject_smoke_test)
        self.assertTrue(request.require_smoke_test_proof)
        self.assertEqual(request.minimum_stability_seconds, 60)

        report = RuntimeLaunchReport(
            status="failed",
            stage="classify",
            instance_path=None,
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version=None,
            java_path=None,
            command_preview=[],
            exit_code=1,
            success_signal=None,
            issues=[
                RuntimeIssue(
                    kind="missing_dependency",
                    severity="fatal",
                    confidence=0.9,
                    message="Missing fabric-api",
                    evidence=["requires mod fabric-api"],
                    missing_mods=["fabric-api"],
                )
            ],
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
            ),
        )

        self.assertIn("missing_dependency", report.model_dump_json())
        self.assertIn("stable_60", report.model_dump_json())


if __name__ == "__main__":
    unittest.main()
