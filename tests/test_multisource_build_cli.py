import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


class MultiSourceBuildCliTests(unittest.TestCase):
    def test_build_from_list_and_agent_pack_help_include_multisource_flags(self):
        from mythweaver.cli.main import _fallback_main

        for command in ["build-from-list", "agent-pack"]:
            stdout = StringIO()
            with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
                _fallback_main([command, "--help"])
            self.assertEqual(raised.exception.code, 0)
            help_text = stdout.getvalue()
            self.assertIn("--sources", help_text)
            self.assertIn("--target-export", help_text)
            self.assertIn("--auto-target", help_text)
            self.assertIn("--candidate-versions", help_text)
            self.assertIn("--candidate-loaders", help_text)


if __name__ == "__main__":
    unittest.main()


class MultiSourceBuildBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_from_list_curseforge_manifest_uses_new_builder(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import SelectedModList, SourceFileCandidate

        class FakeSettings:
            modrinth_user_agent = "MythWeaver-Test"

        class FakeFacade:
            settings = FakeSettings()

        class FakeProvider:
            source_name = "curseforge"

            def is_configured(self):
                return True

            async def resolve_file(self, project_ref, *, minecraft_version, loader):
                return SourceFileCandidate(
                    source="curseforge",
                    project_id="123",
                    file_id="456",
                    name="Curse Mod",
                    acquisition_status="verified_manual_required",
                )

        selected = SelectedModList(
            name="Curse Build",
            minecraft_version="1.20.1",
            loader="forge",
            mods=[{"source": "curseforge", "source_project_id": "123"}],
        )
        output_dir = Path.cwd() / "output" / "test-cf-build-from-list"

        with patch("mythweaver.sources.resolver.provider_for_source", lambda source, **kwargs: FakeProvider()):
            report = await AgentModpackService(FakeFacade()).build_from_list(
                selected,
                output_dir,
                sources=["curseforge"],
                target_export="curseforge_manifest",
                loader_version="47.2.0",
            )

        self.assertEqual(report.status, "completed")
        self.assertTrue(any(artifact.kind == "curseforge-manifest" for artifact in report.generated_artifacts))
