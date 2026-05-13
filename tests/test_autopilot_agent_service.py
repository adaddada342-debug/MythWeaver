import unittest
from pathlib import Path
from unittest.mock import patch


class AutopilotAgentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_service_adapter_delegates_to_autopilot_loop(self):
        from mythweaver.autopilot.contracts import AutopilotReport
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import SelectedModList

        selected = SelectedModList(name="Adapter Pack", minecraft_version="1.20.1", loader="fabric", mods=[{"slug": "a"}])
        output_root = Path(".test-output") / "autopilot-adapter"
        captured = {}

        async def fake_run(request):
            captured["request"] = request
            return AutopilotReport(
                status="blocked",
                final_minecraft_version="1.20.1",
                final_loader="fabric",
                final_loader_version=None,
                attempts=[],
                final_instance_path=None,
                final_export_path=None,
                summary="Blocked",
                warnings=[],
            )

        with patch("mythweaver.pipeline.agent_service.run_autopilot", fake_run):
            report = await AgentModpackService(object()).build_verify_and_repair_pack(
                selected,
                output_root,
                sources=["modrinth"],
                max_attempts=2,
            )

        self.assertEqual(report.status, "blocked")
        self.assertEqual(captured["request"].sources, ["modrinth"])
        self.assertEqual(captured["request"].max_attempts, 2)
        self.assertTrue(Path(captured["request"].selected_mods_path).is_file())


if __name__ == "__main__":
    unittest.main()
