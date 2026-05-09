import json
import unittest


class ModrinthFacetTests(unittest.TestCase):
    def test_builds_search_facets_for_fabric_mods(self):
        from mythweaver.modrinth.facets import build_search_facets
        from mythweaver.schemas.contracts import SearchPlan

        facets = build_search_facets(
            SearchPlan(
                query="winter survival",
                minecraft_version="1.20.1",
                loader="fabric",
                categories=["adventure", "worldgen"],
                client_side="required",
                server_side="optional",
            )
        )

        decoded = json.loads(facets)
        self.assertIn(["project_type:mod"], decoded)
        self.assertIn(["versions:1.20.1"], decoded)
        self.assertIn(["categories:fabric"], decoded)
        self.assertIn(["client_side:required"], decoded)
        self.assertIn(["server_side:optional"], decoded)
        self.assertIn(["categories:adventure", "categories:worldgen"], decoded)

    def test_auto_minecraft_version_omits_version_facet(self):
        from mythweaver.modrinth.facets import build_search_facets
        from mythweaver.schemas.contracts import SearchPlan

        facets = json.loads(build_search_facets(SearchPlan(query="dragons")))

        self.assertNotIn(["versions:auto"], facets)


if __name__ == "__main__":
    unittest.main()
