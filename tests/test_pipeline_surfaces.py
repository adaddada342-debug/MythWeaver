import unittest
from pathlib import Path


class PipelineSurfaceTests(unittest.TestCase):
    def test_facade_lists_generation_tool(self):
        from mythweaver.core.settings import Settings
        from mythweaver.tools.facade import AgentToolFacade

        cache_db = Path.cwd() / "output" / "test-pipeline-surfaces" / "cache.sqlite3"
        facade = AgentToolFacade(Settings(cache_db=cache_db))
        names = {tool["name"] for tool in facade.list_tools()}

        self.assertIn("generate_modpack", names)

    def test_mcp_definitions_include_generation_tools(self):
        from mythweaver.mcp.server import tool_definitions

        names = {tool["name"] for tool in tool_definitions()}

        self.assertIn("generate_modpack", names)
        self.assertIn("plan_modpack_searches", names)
        self.assertIn("discover_candidates", names)
        self.assertIn("expand_dependencies", names)


if __name__ == "__main__":
    unittest.main()
