import unittest


def version_payload(
    project_id: str,
    *,
    loaders=None,
    game_versions=None,
    status="listed",
    filename=None,
    url=None,
    dependencies=None,
):
    return {
        "id": f"{project_id}-version",
        "project_id": project_id,
        "version_number": "1.0.0",
        "game_versions": game_versions or ["1.20.1"],
        "loaders": loaders or ["fabric"],
        "version_type": "release",
        "status": status,
        "dependencies": dependencies or [],
        "files": [
            {
                "filename": filename or f"{project_id}.jar",
                "url": url or f"https://cdn.modrinth.com/data/{project_id}/versions/1/{project_id}.jar",
                "hashes": {"sha1": "a" * 40, "sha512": "b" * 128},
                "size": 123,
                "primary": True,
            }
        ],
    }


class FakeModrinth:
    def __init__(self):
        self.searches = {
            "winter": {
                "hits": [
                    {
                        "project_id": "winter",
                        "slug": "winter",
                        "title": "Winter",
                        "description": "winter survival",
                        "categories": ["adventure"],
                        "client_side": "required",
                        "server_side": "optional",
                        "downloads": 100,
                        "follows": 10,
                        "versions": ["1.20.1"],
                    }
                ]
            }
        }
        self.versions = {"winter": [version_payload("winter")]}

    async def search_projects(self, plan):
        return self.searches.get(plan.query, {"hits": []})

    async def list_project_versions(self, project_id_or_slug, *, loader, minecraft_version, include_changelog=False):
        return self.versions.get(project_id_or_slug, [])


class PipelineDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovers_verified_candidates_from_search_and_versions(self):
        from mythweaver.pipeline.discovery import discover_candidates
        from mythweaver.pipeline.profile import profile_from_prompt
        from mythweaver.pipeline.strategy import build_search_strategy

        modrinth = FakeModrinth()
        profile = profile_from_prompt("winter survival")
        strategy = build_search_strategy(profile, limit=10)
        strategy.search_plans = [strategy.search_plans[0].model_copy(update={"query": "winter"})]

        result = await discover_candidates(modrinth, strategy)

        self.assertEqual(result.minecraft_version, "1.20.1")
        self.assertEqual(result.candidates[0].project_id, "winter")

    async def test_rejects_uninstallable_versions(self):
        from mythweaver.pipeline.discovery import discover_candidates
        from mythweaver.pipeline.profile import profile_from_prompt
        from mythweaver.pipeline.strategy import build_search_strategy

        modrinth = FakeModrinth()
        modrinth.versions["winter"] = [
            version_payload("winter", loaders=["forge"]),
            version_payload("winter", url="http://bad.example/winter.jar"),
            version_payload("winter", status="draft"),
        ]
        profile = profile_from_prompt("winter survival")
        strategy = build_search_strategy(profile, limit=10)
        strategy.search_plans = [strategy.search_plans[0].model_copy(update={"query": "winter"})]

        result = await discover_candidates(modrinth, strategy)

        self.assertEqual(result.candidates, [])
        self.assertTrue(result.rejected)


if __name__ == "__main__":
    unittest.main()
