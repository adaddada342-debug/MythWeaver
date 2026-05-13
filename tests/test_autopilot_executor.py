import unittest
from unittest.mock import patch


class AutopilotExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_mod_updates_working_selection_without_mutating_original(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.executor import apply_runtime_actions
        from mythweaver.runtime.contracts import RuntimeAction
        from mythweaver.schemas.contracts import SelectedModList

        original = SelectedModList(name="Pack", minecraft_version="1.20.1", loader="fabric", mods=[{"slug": "cameraoverhaul"}])
        async def fake_resolve(selected, **kwargs):
            from mythweaver.schemas.contracts import SourceFileCandidate, SourceResolveReport

            return SourceResolveReport(
                status="resolved",
                minecraft_version=kwargs["minecraft_version"],
                loader=kwargs["loader"],
                selected_files=[
                    SourceFileCandidate(
                        source="modrinth",
                        name="Fabric API",
                        slug="fabric-api",
                        download_url="https://cdn.modrinth.com/fabric-api.jar",
                        hashes={"sha1": "0" * 40},
                        acquisition_status="verified_auto",
                    )
                ],
                export_supported=True,
                dependency_closure_passed=True,
            )

        with patch("mythweaver.autopilot.executor.resolve_sources_for_selected_mods", fake_resolve):
            working, applied = await apply_runtime_actions(
                original,
                [RuntimeAction(action="add_mod", safety="safe", reason="missing dependency", query="fabric-api")],
                AutopilotRequest(selected_mods_path="selected_mods.json", sources=["modrinth"]),
                minecraft_version="1.20.1",
                loader="fabric",
            )

        self.assertEqual([mod.slug for mod in original.mods], ["cameraoverhaul"])
        self.assertEqual([mod.slug for mod in working.mods], ["cameraoverhaul", "fabric-api"])
        self.assertEqual(applied[0].status, "applied")

    async def test_add_mod_blocks_when_preflight_is_manual_or_blocked(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.executor import apply_runtime_actions
        from mythweaver.runtime.contracts import RuntimeAction
        from mythweaver.schemas.contracts import SelectedModList, SourceFileCandidate, SourceResolveReport

        async def fake_resolve(selected, **kwargs):
            manual = SourceFileCandidate(
                source="curseforge",
                name="Manifest Only",
                project_id="123",
                file_id="456",
                acquisition_status="verified_manual_required",
            )
            return SourceResolveReport(
                status="partial",
                minecraft_version=kwargs["minecraft_version"],
                loader=kwargs["loader"],
                manual_required=[manual],
                export_supported=False,
                export_blockers=["manual acquisition required"],
            )

        original = SelectedModList(name="Pack", minecraft_version="1.20.1", loader="fabric", mods=[{"slug": "cameraoverhaul"}])
        with patch("mythweaver.autopilot.executor.resolve_sources_for_selected_mods", fake_resolve):
            working, applied = await apply_runtime_actions(
                original,
                [RuntimeAction(action="add_mod", safety="safe", reason="missing dependency", query="manifest-only")],
                AutopilotRequest(selected_mods_path="selected_mods.json", sources=["curseforge"]),
                minecraft_version="1.20.1",
                loader="fabric",
            )

        self.assertEqual([mod.slug for mod in working.mods], ["cameraoverhaul"])
        self.assertEqual(applied[0].status, "blocked")
        self.assertIn("preflight", applied[0].reason.lower())

    async def test_add_mod_blocks_direct_url_query_before_preflight(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.executor import apply_runtime_actions
        from mythweaver.runtime.contracts import RuntimeAction
        from mythweaver.schemas.contracts import SelectedModList

        original = SelectedModList(name="Pack", minecraft_version="1.20.1", loader="fabric", mods=[])
        working, applied = await apply_runtime_actions(
            original,
            [RuntimeAction(action="add_mod", safety="safe", reason="bad", query="https://example.invalid/mod.jar")],
            AutopilotRequest(selected_mods_path="selected_mods.json", sources=["direct_url"]),
            minecraft_version="1.20.1",
            loader="fabric",
        )

        self.assertEqual(working.mods, [])
        self.assertEqual(applied[0].status, "blocked")

    async def test_remove_mod_is_blocked_for_content_mods_by_default(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.executor import apply_runtime_actions
        from mythweaver.runtime.contracts import RuntimeAction
        from mythweaver.schemas.contracts import SelectedModList

        original = SelectedModList(name="Pack", minecraft_version="1.20.1", loader="fabric", mods=[{"slug": "content-mod"}])
        working, applied = await apply_runtime_actions(
            original,
            [RuntimeAction(action="remove_mod", safety="safe", reason="remove content", query="content-mod")],
            AutopilotRequest(selected_mods_path="selected_mods.json", sources=["modrinth"]),
            minecraft_version="1.20.1",
            loader="fabric",
        )

        self.assertEqual([mod.slug for mod in working.mods], ["content-mod"])
        self.assertEqual(applied[0].status, "blocked")

    async def test_remove_mod_exact_duplicate_requires_content_removal_flag(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.executor import apply_runtime_actions
        from mythweaver.runtime.contracts import RuntimeAction
        from mythweaver.schemas.contracts import SelectedModList

        original = SelectedModList(
            name="Pack",
            minecraft_version="1.20.1",
            loader="fabric",
            mods=[{"slug": "duplicate-lib", "role": "dependency"}, {"slug": "duplicate-lib", "role": "dependency"}],
        )
        working, applied = await apply_runtime_actions(
            original,
            [RuntimeAction(action="remove_mod", safety="safe", reason="exact duplicate", query="duplicate-lib")],
            AutopilotRequest(selected_mods_path="selected_mods.json", sources=["modrinth"], allow_remove_content_mods=True),
            minecraft_version="1.20.1",
            loader="fabric",
        )

        self.assertEqual([mod.slug for mod in original.mods], ["duplicate-lib", "duplicate-lib"])
        self.assertEqual([mod.slug for mod in working.mods], ["duplicate-lib"])
        self.assertEqual(applied[0].status, "applied")


if __name__ == "__main__":
    unittest.main()
