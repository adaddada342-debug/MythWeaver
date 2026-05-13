import unittest
import asyncio
from pathlib import Path


class AgentToolFacadeTests(unittest.TestCase):
    def test_lists_deterministic_tools_without_ai_provider(self):
        from mythweaver.core.settings import Settings
        from mythweaver.tools.facade import AgentToolFacade

        cache_db = Path.cwd() / "output" / "test-agent-tools" / "cache.sqlite3"
        facade = AgentToolFacade(settings=Settings(cache_db=cache_db))
        tool_names = {tool["name"] for tool in facade.list_tools()}

        self.assertIn("search_modrinth", tool_names)
        self.assertIn("resolve_dependencies", tool_names)
        self.assertIn("analyze_failure", tool_names)
        self.assertFalse(facade.settings.ai_enabled)

    def test_build_pack_can_export_manifest_without_downloading(self):
        from mythweaver.core.settings import Settings
        from mythweaver.schemas.contracts import ResolvedPack
        from mythweaver.tools.facade import AgentToolFacade

        from tests.test_scoring import candidate

        output_dir = Path.cwd() / "output" / "test-agent-build"
        facade = AgentToolFacade(settings=Settings(cache_db=output_dir / "cache.sqlite3"))
        pack = ResolvedPack(
            name="Agent Pack",
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version="0.15.11",
            selected_mods=[candidate("agent1", "Agent Mod", "Magic")],
        )

        artifacts = asyncio.run(facade.build_pack(pack, output_dir, download=False))

        mrpack = next(a for a in artifacts if a.kind == "mrpack")
        self.assertTrue(Path(mrpack.path).is_file())
        report = next(a for a in artifacts if a.kind == "final-artifact-validation-report")
        self.assertEqual(report.metadata.get("status"), "skipped")
        self.assertTrue(Path(report.path).is_file())


if __name__ == "__main__":
    unittest.main()
