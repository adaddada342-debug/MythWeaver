import unittest

from tests.test_scoring import candidate


class VersionPolicyTests(unittest.TestCase):
    def test_selects_version_with_best_candidate_coverage(self):
        from mythweaver.catalog.version_policy import select_minecraft_version

        choice = select_minecraft_version(
            [
                candidate("a", "A", "Magic", game_versions=["1.20.1", "1.20.4"]),
                candidate("b", "B", "Worldgen", game_versions=["1.20.4"]),
                candidate("c", "C", "Mobs", game_versions=["1.19.2"]),
            ],
            preferred_versions=["1.20.4", "1.20.1", "1.19.2"],
        )

        self.assertEqual(choice.version, "1.20.4")
        self.assertEqual(choice.supporting_project_ids, ["a", "b"])


if __name__ == "__main__":
    unittest.main()
