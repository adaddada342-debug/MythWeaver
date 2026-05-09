import unittest

from tests.test_scoring import candidate


class ConflictDetectionTests(unittest.TestCase):
    def test_reports_duplicate_functionality_groups(self):
        from mythweaver.core.settings import Settings
        from mythweaver.tools.facade import AgentToolFacade

        cache_db = __import__("pathlib").Path.cwd() / "output" / "test-conflicts" / "cache.sqlite3"
        facade = AgentToolFacade(Settings(cache_db=cache_db))
        conflicts = facade.detect_conflicts(
            [
                candidate("fast1", "Fast One", "Optimization", categories=["optimization"]),
                candidate("fast2", "Fast Two", "Performance", categories=["performance"]),
            ]
        )

        self.assertEqual(conflicts[0]["group"], "performance")
        self.assertEqual(conflicts[0]["reason"], "duplicate_functionality")

    def test_selection_rejects_duplicate_shader_loaders_and_renderer_replacements(self):
        from mythweaver.pipeline.selection import select_candidates

        selection = select_candidates(
            [
                candidate("iris", "Iris Shaders", "Shader loader support", categories=["optimization"]),
                candidate("shader2", "Alternate Shader Loader", "Another shader loader", categories=["utility"]),
                candidate("sodium", "Sodium", "Renderer optimization replacement", categories=["optimization"]),
                candidate("renderer2", "Alternate Renderer", "Renderer replacement", categories=["optimization"]),
            ],
            max_mods=10,
        )

        self.assertIn("iris", selection.selected_project_ids)
        self.assertIn("sodium", selection.selected_project_ids)
        self.assertNotIn("shader2", selection.selected_project_ids)
        self.assertNotIn("renderer2", selection.selected_project_ids)
        self.assertTrue(any(rejection.detail == "shader_loader" for rejection in selection.rejected_mods))
        self.assertTrue(any(rejection.detail == "renderer_optimization" for rejection in selection.rejected_mods))


if __name__ == "__main__":
    unittest.main()
