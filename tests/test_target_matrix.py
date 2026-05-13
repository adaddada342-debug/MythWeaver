import unittest
from unittest.mock import patch


class TargetMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def test_target_matrix_chooses_highest_verified_coverage(self):
        from mythweaver.catalog.target_matrix import build_target_matrix
        from mythweaver.schemas.contracts import SelectedModList, SourceFileCandidate, SourceResolveReport

        selected = SelectedModList(
            name="Any Pack",
            minecraft_version="any",
            loader="any",
            mods=[{"slug": "a"}, {"slug": "b"}],
        )

        async def fake_resolve(selected, *, minecraft_version, loader, sources, target_export, autonomous, modrinth=None, curseforge_api_key=None, allow_manual_sources=False):
            count = 2 if (minecraft_version, loader) == ("1.20.1", "forge") else 1
            files = [
                SourceFileCandidate(source="modrinth", project_id=f"p{i}", name=f"Mod {i}", acquisition_status="verified_auto")
                for i in range(count)
            ]
            return SourceResolveReport(
                status="resolved" if count == 2 else "partial",
                minecraft_version=minecraft_version,
                loader=loader,
                selected_files=files,
                required_count=2,
                dependency_closure_passed=count == 2,
                export_supported=count == 2,
            )

        with patch("mythweaver.catalog.target_matrix.resolve_sources_for_selected_mods", fake_resolve):
            report = await build_target_matrix(
                selected,
                sources=["modrinth", "curseforge"],
                candidate_versions=["1.19.2", "1.20.1"],
                candidate_loaders=["fabric", "forge"],
                target_export="local_instance",
            )

        self.assertEqual(report.status, "resolved")
        self.assertEqual(report.best.minecraft_version, "1.20.1")
        self.assertEqual(report.best.loader, "forge")
        self.assertEqual(report.best.selected_count, 2)

    async def test_target_matrix_fixed_loader_does_not_evaluate_other_loaders(self):
        from mythweaver.catalog.target_matrix import build_target_matrix
        from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport

        selected = SelectedModList(name="Fixed Pack", minecraft_version="1.20.1", loader="fabric", mods=[{"slug": "a"}])
        calls = []

        async def fake_resolve(selected, *, minecraft_version, loader, sources, target_export, autonomous, modrinth=None, curseforge_api_key=None, allow_manual_sources=False):
            calls.append((minecraft_version, loader))
            return SourceResolveReport(
                status="failed",
                minecraft_version=minecraft_version,
                loader=loader,
                required_count=1,
            )

        with patch("mythweaver.catalog.target_matrix.resolve_sources_for_selected_mods", fake_resolve):
            report = await build_target_matrix(
                selected,
                sources=["modrinth"],
                candidate_versions=["1.20.1", "1.19.2"],
                candidate_loaders=["fabric", "forge", "quilt"],
                target_export="local_instance",
            )

        self.assertEqual(calls, [("1.20.1", "fabric")])
        self.assertEqual(report.considered_loaders, ["fabric"])

    async def test_target_matrix_does_not_invent_versions_without_real_candidates(self):
        from mythweaver.catalog.target_matrix import build_target_matrix
        from mythweaver.schemas.contracts import SelectedModList

        selected = SelectedModList(name="Any Pack", minecraft_version="any", loader="any", mods=[{"slug": "a"}])

        report = await build_target_matrix(
            selected,
            sources=["modrinth"],
            candidate_versions=None,
            candidate_loaders=["fabric"],
            target_export="local_instance",
            modrinth=None,
        )

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.considered_versions, [])
        self.assertIn("No target candidates", " ".join(report.warnings))

    async def test_target_matrix_failed_candidates_emit_actionable_warning(self):
        from mythweaver.catalog.target_matrix import build_target_matrix
        from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport

        selected = SelectedModList(name="Blocked Pack", minecraft_version="any", loader="any", mods=[{"slug": "a"}])

        async def fake_resolve(selected, *, minecraft_version, loader, sources, target_export, autonomous, modrinth=None, curseforge_api_key=None, allow_manual_sources=False):
            return SourceResolveReport(
                status="failed",
                minecraft_version=minecraft_version,
                loader=loader,
                required_count=1,
                unsupported_count=1,
                dependency_closure_passed=False,
                export_supported=False,
            )

        with patch("mythweaver.catalog.target_matrix.resolve_sources_for_selected_mods", fake_resolve):
            report = await build_target_matrix(
                selected,
                sources=["modrinth"],
                candidate_versions=["1.20.1"],
                candidate_loaders=["fabric"],
                target_export="local_instance",
            )

        self.assertEqual(report.status, "failed")
        self.assertIsNotNone(report.best)
        self.assertIn("No target candidate produced exportable", " ".join(report.warnings))


if __name__ == "__main__":
    unittest.main()
