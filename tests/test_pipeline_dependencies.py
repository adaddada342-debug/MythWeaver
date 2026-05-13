import unittest

from tests.test_pipeline_discovery import version_payload
from tests.test_scoring import candidate


class DependencyModrinth:
    async def get_project(self, project_id_or_slug):
        if project_id_or_slug == "fabric-api":
            return {
                "id": "fabric-api",
                "project_id": "fabric-api",
                "slug": "fabric-api",
                "title": "Fabric API",
                "description": "Core Fabric library.",
                "categories": ["library"],
                "client_side": "required",
                "server_side": "required",
                "downloads": 100,
                "follows": 10,
                "versions": ["1.20.1"],
            }
        return {}

    async def list_project_versions(self, project_id_or_slug, *, loader, minecraft_version, include_changelog=False, use_loader_filter=True, **kwargs):
        if project_id_or_slug == "fabric-api":
            return [version_payload("fabric-api", game_versions=[minecraft_version])]
        return []


class PipelineDependencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_expands_missing_required_dependency_from_modrinth(self):
        from mythweaver.pipeline.dependencies import expand_required_dependencies
        from mythweaver.schemas.contracts import DependencyRecord, RequirementProfile

        main = candidate("main", "Main", "Requires Fabric API")
        main.selected_version.dependencies.append(
            DependencyRecord(project_id="fabric-api", dependency_type="required")
        )
        expanded, rejected = await expand_required_dependencies(
            DependencyModrinth(),
            [main],
            RequirementProfile(name="Dependency Pack", themes=["utility"], minecraft_version="1.20.1"),
            "1.20.1",
        )

        self.assertEqual({mod.project_id for mod in expanded}, {"main", "fabric-api"})
        self.assertEqual(rejected, [])


if __name__ == "__main__":
    unittest.main()
