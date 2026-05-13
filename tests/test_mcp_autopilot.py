import unittest
from pathlib import Path
from unittest.mock import patch


class McpAutopilotTests(unittest.IsolatedAsyncioTestCase):
    def test_tools_list_includes_canonical_autopilot_tool(self):
        from mythweaver.mcp.server import tool_definitions

        names = {tool["name"] for tool in tool_definitions()}
        self.assertIn("run_autopilot", names)
        self.assertIn("get_autopilot_run", names)

    async def test_run_autopilot_tool_returns_json_compatible_report(self):
        from mythweaver.autopilot.contracts import AutopilotReport
        from mythweaver.mcp.server import _jsonable, call_tool

        root = Path(".test-output") / "mcp-autopilot"
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
            run_id="mcp_run",
            run_dir=str(root / "runs" / "mcp_run"),
            timeline_path=str(root / "runs" / "mcp_run" / "timeline.jsonl"),
            report_paths={"json": str(root / "runs" / "mcp_run" / "autopilot_report.json")},
        )

        async def fake_run(request):
            return fake_report

        with patch("mythweaver.mcp.server.run_autopilot", fake_run):
            result = await call_tool(
                object(),  # type: ignore[arg-type]
                "run_autopilot",
                {
                    "selected_mods_path": str(root / "selected_mods.json"),
                    "sources": ["local"],
                    "minecraft_version": "1.20.1",
                    "loader": "fabric",
                },
            )

        jsonable = _jsonable(result)
        self.assertEqual(jsonable["run_id"], "mcp_run")
        self.assertEqual(jsonable["status"], "blocked")
        self.assertIn("report_paths", jsonable)
        self.assertIn("attempts", jsonable)
        self.assertIn("blockers", jsonable)


if __name__ == "__main__":
    unittest.main()
