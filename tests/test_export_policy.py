import unittest


class ExportPolicyTests(unittest.TestCase):
    def candidate(self, **overrides):
        from mythweaver.schemas.contracts import SourceFileCandidate

        data = {
            "source": "modrinth",
            "name": "Test Mod",
            "project_id": "project",
            "file_id": "file",
            "download_url": "https://example.invalid/test.jar",
            "hashes": {"sha1": "a" * 40, "sha512": "b" * 128},
            "acquisition_status": "verified_auto",
        }
        data.update(overrides)
        return SourceFileCandidate(**data)

    def test_modrinth_pack_requires_modrinth_downloadable_file(self):
        from mythweaver.sources.policy import evaluate_candidate_policy

        curseforge = self.candidate(source="curseforge", project_id="1", file_id="2")

        result = evaluate_candidate_policy(
            curseforge,
            target_export="modrinth_pack",
            autonomous=True,
        )

        self.assertEqual(result.acquisition_status, "download_blocked")
        self.assertIn("Modrinth .mrpack", " ".join(result.warnings))

    def test_curseforge_manifest_allows_project_and_file_without_download_url(self):
        from mythweaver.sources.policy import evaluate_candidate_policy

        curseforge = self.candidate(
            source="curseforge",
            project_id="123",
            file_id="456",
            download_url=None,
            hashes={},
            acquisition_status="verified_manual_required",
        )

        result = evaluate_candidate_policy(
            curseforge,
            target_export="curseforge_manifest",
            autonomous=True,
        )

        self.assertEqual(result.acquisition_status, "verified_manual_required")

    def test_local_instance_requires_hashes_and_auto_download_or_local_file(self):
        from mythweaver.sources.policy import evaluate_candidate_policy

        local = self.candidate(source="local", download_url="C:/mods/test.jar")
        no_hash = self.candidate(source="modrinth", hashes={})
        no_download = self.candidate(source="curseforge", download_url=None)

        self.assertEqual(
            evaluate_candidate_policy(local, target_export="local_instance", autonomous=True).acquisition_status,
            "verified_auto",
        )
        self.assertEqual(
            evaluate_candidate_policy(no_hash, target_export="local_instance", autonomous=True).acquisition_status,
            "metadata_incomplete",
        )
        self.assertEqual(
            evaluate_candidate_policy(no_download, target_export="prism_instance", autonomous=True).acquisition_status,
            "metadata_incomplete",
        )

    def test_direct_url_is_blocked_in_autonomous_mode(self):
        from mythweaver.sources.policy import evaluate_candidate_policy

        direct = self.candidate(source="direct_url", acquisition_status="verified_auto")

        result = evaluate_candidate_policy(direct, target_export="local_instance", autonomous=True)

        self.assertEqual(result.acquisition_status, "download_blocked")
        self.assertIn("Direct URL", " ".join(result.warnings))

    def test_curseforge_manifest_blocks_any_manual_non_manifest_entries(self):
        from mythweaver.sources.resolver import _export_blockers

        blockers = _export_blockers(
            target_export="curseforge_manifest",
            selected_files=[],
            manifest_files=[self.candidate(source="curseforge", project_id="123", file_id="456")],
            manual_required=[self.candidate(source="curseforge", project_id="789", file_id=None)],
            blocked=[],
            unresolved_required_dependencies=[],
        )

        self.assertIn("Manual files are not CurseForge manifest-eligible.", blockers)


if __name__ == "__main__":
    unittest.main()
