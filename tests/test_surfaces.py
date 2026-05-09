import unittest
import asyncio
from pathlib import Path


class SurfaceImportTests(unittest.TestCase):
    def test_surface_modules_import_without_optional_ai_or_ui_dependencies(self):
        import mythweaver.api.app
        import mythweaver.cli.main
        import mythweaver.cli.tui
        import mythweaver.mcp.server

        self.assertTrue(hasattr(mythweaver.api.app, "create_app"))
        self.assertTrue(hasattr(mythweaver.cli.main, "main"))
        self.assertTrue(hasattr(mythweaver.cli.tui, "run_tui"))
        self.assertTrue(hasattr(mythweaver.mcp.server, "tool_definitions"))

    def test_mcp_tool_definitions_are_agent_readable(self):
        from mythweaver.mcp.server import tool_definitions

        definitions = tool_definitions()
        names = {definition["name"] for definition in definitions}

        self.assertIn("search_modrinth", names)
        self.assertIn("build_pack", names)
        self.assertIn("analyze_failure", names)

    def test_mcp_call_tool_uses_real_facade_service(self):
        from mythweaver.core.settings import Settings
        from mythweaver.mcp.server import call_tool
        from mythweaver.tools.facade import AgentToolFacade

        output_dir = Path.cwd() / "output" / "test-mcp-call"
        facade = AgentToolFacade(Settings(cache_db=output_dir / "cache.sqlite3"))

        result = asyncio.run(
            call_tool(
                facade,
                "analyze_failure",
                {"log_text": "Mixin apply failed for mod sodium"},
            )
        )

        self.assertEqual(result.classification, "mixin_failure")


if __name__ == "__main__":
    unittest.main()
