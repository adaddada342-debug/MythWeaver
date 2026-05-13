import unittest
from pathlib import Path
from unittest.mock import patch


class ApiAutopilotTests(unittest.TestCase):
    def test_post_autopilot_run_returns_report_json(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("FastAPI test client is not installed")

        from mythweaver.api.app import create_app
        from mythweaver.autopilot.contracts import AutopilotReport

        root = Path(".test-output") / "api-autopilot"
        fake_report = AutopilotReport(
            status="blocked",
            final_minecraft_version="1.20.1",
            final_loader="fabric",
            final_loader_version=None,
            attempts=[],
            final_instance_path=None,
            final_export_path=None,
            summary="Blocked",
            warnings=[],
            run_id="api_run",
            run_dir=str(root / "runs" / "api_run"),
            timeline_path=str(root / "runs" / "api_run" / "timeline.jsonl"),
            report_paths={"json": str(root / "runs" / "api_run" / "autopilot_report.json")},
        )

        async def fake_run(request):
            return fake_report

        with patch("mythweaver.api.app.run_autopilot", fake_run):
            client = TestClient(create_app())
            response = client.post(
                "/v1/autopilot/run",
                json={
                    "selected_mods_path": str(root / "selected_mods.json"),
                    "sources": ["local"],
                    "minecraft_version": "1.20.1",
                    "loader": "fabric",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["run_id"], "api_run")
        self.assertEqual(payload["status"], "blocked")
        self.assertIn("report_paths", payload)


if __name__ == "__main__":
    unittest.main()
