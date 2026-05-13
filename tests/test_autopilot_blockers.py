import unittest
from pathlib import Path
from unittest.mock import patch


class AutopilotBlockerTests(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_runtime_loader_creates_machine_readable_blocker(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.loop import run_autopilot
        from mythweaver.runtime.contracts import RuntimeIssue, RuntimeLaunchReport
        from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport

        root = Path(".test-output") / "autopilot-blocker-unsupported"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(name="Unsupported", minecraft_version="1.20.1", loader="forge", mods=[]).model_dump_json(),
            encoding="utf-8",
        )

        async def fake_resolve(selected, **kwargs):
            return SourceResolveReport(
                status="resolved",
                minecraft_version=kwargs["minecraft_version"],
                loader=kwargs["loader"],
                selected_files=[],
                export_supported=True,
                dependency_closure_passed=True,
            )

        def fake_runtime(request):
            return RuntimeLaunchReport(
                status="failed",
                stage="install_loader",
                instance_path=None,
                minecraft_version=request.minecraft_version,
                loader=request.loader,
                loader_version=None,
                java_path=None,
                command_preview=[],
                exit_code=None,
                success_signal=None,
                issues=[
                    RuntimeIssue(
                        kind="unsupported_loader_runtime",
                        severity="fatal",
                        confidence=1.0,
                        message="Forge is unsupported in private runtime V1.",
                        evidence=["loader=forge"],
                    )
                ],
                recommended_next_actions=[],
                logs_scanned=[],
                warnings=[],
            )

        with (
            patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", fake_resolve),
            patch("mythweaver.autopilot.loop.run_runtime_validation", fake_runtime),
        ):
            report = await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    output_root=str(root),
                    minecraft_version="1.20.1",
                    loader="forge",
                    sources=["local"],
                    max_attempts=1,
                )
            )

        self.assertEqual(report.status, "blocked")
        self.assertIn("unsupported_loader_runtime", {blocker.kind for blocker in report.blockers})
        blocker = next(item for item in report.blockers if item.kind == "unsupported_loader_runtime")
        self.assertTrue(blocker.user_action_required)

    async def test_source_policy_block_creates_blocker(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.loop import run_autopilot
        from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport

        root = Path(".test-output") / "autopilot-blocker-source"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(name="Policy", minecraft_version="1.20.1", loader="fabric", mods=[]).model_dump_json(),
            encoding="utf-8",
        )

        async def fake_resolve(selected, **kwargs):
            return SourceResolveReport(
                status="failed",
                minecraft_version=kwargs["minecraft_version"],
                loader=kwargs["loader"],
                export_supported=False,
                export_blockers=["direct_url is blocked for autonomous runtime install"],
            )

        with patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", fake_resolve):
            report = await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    output_root=str(root),
                    minecraft_version="1.20.1",
                    loader="fabric",
                    sources=["direct_url"],
                    max_attempts=1,
                )
            )

        self.assertEqual(report.status, "blocked")
        self.assertEqual(report.blockers[0].kind, "source_policy_blocked")
        self.assertIn("direct_url", report.blockers[0].data["evidence"][0])


if __name__ == "__main__":
    unittest.main()
