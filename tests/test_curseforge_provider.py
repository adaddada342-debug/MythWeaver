import unittest


def _provider(payloads):
    from mythweaver.sources.curseforge import CurseForgeSourceProvider

    def request(path, params=None):
        key = (path, tuple(sorted((params or {}).items())))
        return payloads.get(key) or payloads[path]

    return CurseForgeSourceProvider(api_key="test", request_json=request)


def _mod_payload(mod_id=10, slug="mock-mod"):
    return {"data": {"id": mod_id, "slug": slug, "name": "Mock Mod"}}


def _file(file_id, *, loader, version="1.20.1", release_type=1, download_url="https://edge.forgecdn.net/files/mock.jar"):
    return {
        "id": file_id,
        "displayName": f"Mock {loader} {file_id}",
        "fileName": f"mock-{file_id}.jar",
        "downloadUrl": download_url,
        "gameVersions": [version, loader],
        "releaseType": release_type,
        "fileDate": f"2024-01-{file_id:02d}T00:00:00Z",
        "hashes": [{"algo": 1, "value": "a" * 40}],
        "fileLength": 1234,
    }


class CurseForgeProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_matching_fabric_file(self):
        provider = _provider(
            {
                "/v1/mods/10": _mod_payload(),
                "/v1/mods/10/files": {"data": [_file(1, loader="Fabric")]},
            }
        )

        candidate = await provider.resolve_file("10", minecraft_version="1.20.1", loader="fabric")

        self.assertEqual(candidate.acquisition_status, "verified_auto")
        self.assertEqual(candidate.file_id, "1")
        self.assertEqual(candidate.loaders, ["fabric"])

    async def test_resolves_matching_forge_file(self):
        provider = _provider(
            {
                "/v1/mods/10": _mod_payload(),
                "/v1/mods/10/files": {"data": [_file(2, loader="Forge")]},
            }
        )

        candidate = await provider.resolve_file("10", minecraft_version="1.20.1", loader="forge")

        self.assertEqual(candidate.acquisition_status, "verified_auto")
        self.assertEqual(candidate.loaders, ["forge"])

    async def test_rejects_wrong_loader(self):
        provider = _provider(
            {
                "/v1/mods/10": _mod_payload(),
                "/v1/mods/10/files": {"data": [_file(3, loader="Forge")]},
            }
        )

        candidate = await provider.resolve_file("10", minecraft_version="1.20.1", loader="fabric")

        self.assertEqual(candidate.acquisition_status, "unsupported")

    async def test_prefers_release_over_newer_beta(self):
        provider = _provider(
            {
                "/v1/mods/10": _mod_payload(),
                "/v1/mods/10/files": {
                    "data": [
                        _file(20, loader="Fabric", release_type=2),
                        _file(10, loader="Fabric", release_type=1),
                    ]
                },
            }
        )

        candidate = await provider.resolve_file("10", minecraft_version="1.20.1", loader="fabric")

        self.assertEqual(candidate.file_id, "10")

    async def test_manifest_eligible_without_download_url(self):
        provider = _provider(
            {
                "/v1/mods/10": _mod_payload(),
                "/v1/mods/10/files": {"data": [_file(4, loader="Fabric", download_url=None)]},
            }
        )

        candidate = await provider.resolve_file("10", minecraft_version="1.20.1", loader="fabric")

        self.assertEqual(candidate.acquisition_status, "verified_manual_required")
        self.assertEqual(candidate.project_id, "10")
        self.assertEqual(candidate.file_id, "4")

    async def test_dependency_records_preserve_relation_types(self):
        file_data = _file(5, loader="Fabric")
        file_data["dependencies"] = [
            {"modId": 11, "relationType": 3},
            {"modId": 12, "relationType": 2},
            {"modId": 13, "relationType": 4},
            {"modId": 14, "relationType": 5},
        ]
        provider = _provider(
            {
                "/v1/mods/10": _mod_payload(),
                "/v1/mods/10/files": {"data": [file_data]},
            }
        )

        candidate = await provider.resolve_file("10", minecraft_version="1.20.1", loader="fabric")

        by_id = {record.project_id: record.dependency_type for record in candidate.dependency_records}
        self.assertEqual(by_id["11"], "required")
        self.assertEqual(by_id["12"], "optional")
        self.assertEqual(by_id["13"], "incompatible")
        self.assertEqual(by_id["14"], "embedded")

    async def test_mod_loader_type_match_remains_installable_without_loader_game_version(self):
        file_data = _file(6, loader="Fabric")
        file_data["gameVersions"] = ["1.20.1"]
        file_data["modLoaderType"] = 4
        provider = _provider(
            {
                "/v1/mods/10": _mod_payload(),
                "/v1/mods/10/files": {"data": [file_data]},
            }
        )

        candidate = await provider.resolve_file("10", minecraft_version="1.20.1", loader="fabric")

        self.assertEqual(candidate.acquisition_status, "verified_auto")
        self.assertEqual(candidate.loaders, ["fabric"])


if __name__ == "__main__":
    unittest.main()
