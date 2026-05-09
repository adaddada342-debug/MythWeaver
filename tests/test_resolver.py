import unittest

from tests.test_scoring import candidate


class ResolverTests(unittest.TestCase):
    def test_adds_required_dependencies_from_candidate_pool(self):
        from mythweaver.resolver.engine import resolve_pack
        from mythweaver.schemas.contracts import DependencyRecord, RequirementProfile

        main = candidate("mainmod", "Main Mod", "Magic progression")
        dep = candidate("fabricapi", "Fabric API", "Required library")
        main.selected_version.dependencies.append(
            DependencyRecord(project_id="fabricapi", dependency_type="required")
        )

        resolved = resolve_pack(
            requested_project_ids=["mainmod"],
            candidates=[main, dep],
            profile=RequirementProfile(name="Magic", themes=["magic"], minecraft_version="1.20.1"),
        )

        self.assertEqual([mod.project_id for mod in resolved.selected_mods], ["mainmod", "fabricapi"])
        self.assertEqual(resolved.dependency_edges[0].source_project_id, "mainmod")
        self.assertEqual(resolved.dependency_edges[0].target_project_id, "fabricapi")

    def test_reports_missing_required_dependency(self):
        from mythweaver.resolver.engine import resolve_pack
        from mythweaver.schemas.contracts import DependencyRecord, RequirementProfile

        main = candidate("mainmod", "Main Mod", "Magic progression")
        main.selected_version.dependencies.append(
            DependencyRecord(project_id="missinglib", dependency_type="required")
        )

        resolved = resolve_pack(
            requested_project_ids=["mainmod"],
            candidates=[main],
            profile=RequirementProfile(name="Magic", themes=["magic"], minecraft_version="1.20.1"),
        )

        self.assertEqual(resolved.rejected_mods[0].project_id, "missinglib")
        self.assertEqual(resolved.rejected_mods[0].reason, "missing_required_dependency")


if __name__ == "__main__":
    unittest.main()
