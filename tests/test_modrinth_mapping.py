import unittest


class ModrinthMappingTests(unittest.TestCase):
    def test_maps_project_hit_and_version_to_candidate_contract(self):
        from mythweaver.modrinth.client import candidate_from_project_hit

        candidate = candidate_from_project_hit(
            {
                "project_id": "abc12345",
                "slug": "winter",
                "title": "Winter",
                "description": "Snow survival",
                "categories": ["adventure"],
                "client_side": "required",
                "server_side": "optional",
                "downloads": 100,
                "follows": 10,
                "versions": ["1.20.1"],
            },
            {
                "id": "ver12345",
                "project_id": "abc12345",
                "version_number": "1.0.0",
                "game_versions": ["1.20.1"],
                "loaders": ["fabric"],
                "version_type": "release",
                "status": "listed",
                "dependencies": [],
                "files": [
                    {
                        "filename": "winter.jar",
                        "url": "https://cdn.modrinth.com/data/abc12345/versions/1/winter.jar",
                        "hashes": {"sha1": "a" * 40, "sha512": "b" * 128},
                        "size": 11,
                        "primary": True,
                    }
                ],
            },
        )

        self.assertEqual(candidate.project_id, "abc12345")
        self.assertEqual(candidate.primary_file().filename, "winter.jar")


if __name__ == "__main__":
    unittest.main()
