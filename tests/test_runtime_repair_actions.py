import unittest


class RuntimeRepairActionTests(unittest.TestCase):
    def test_missing_dependency_creates_safe_add_mod_action(self):
        from mythweaver.runtime.contracts import RuntimeIssue
        from mythweaver.runtime.repair_actions import actions_for_issues

        actions = actions_for_issues(
            [
                RuntimeIssue(
                    kind="missing_dependency",
                    severity="fatal",
                    confidence=0.9,
                    message="Missing fabric-api",
                    evidence=["requires mod fabric-api"],
                    missing_mods=["fabric-api"],
                )
            ]
        )

        self.assertEqual(actions[0].action, "add_mod")
        self.assertEqual(actions[0].safety, "safe")
        self.assertEqual(actions[0].query, "fabric-api")
        self.assertEqual(actions[0].source_preference, ["modrinth", "curseforge"])

    def test_mixin_failure_requires_manual_review(self):
        from mythweaver.runtime.contracts import RuntimeIssue
        from mythweaver.runtime.repair_actions import actions_for_issues

        actions = actions_for_issues(
            [
                RuntimeIssue(
                    kind="mixin_failure",
                    severity="fatal",
                    confidence=0.8,
                    message="Mixin failed",
                    evidence=["Mixin apply failed"],
                )
            ]
        )

        self.assertEqual(actions[0].action, "manual_review")
        self.assertEqual(actions[0].safety, "manual")

    def test_missing_dependency_diagnosis_creates_safe_add_mod_action(self):
        from mythweaver.runtime.contracts import RuntimeDiagnosis
        from mythweaver.runtime.repair_actions import actions_for_diagnoses

        actions = actions_for_diagnoses(
            [
                RuntimeDiagnosis(
                    kind="fabric_api_missing",
                    confidence="high",
                    summary="Fabric API missing",
                    evidence=["requires mod fabric-api"],
                    affected_mod_ids=["fabric-api"],
                    suggested_repair_action_kinds=["add_mod"],
                )
            ]
        )

        self.assertEqual(actions[0].action, "add_mod")
        self.assertEqual(actions[0].safety, "safe")
        self.assertEqual(actions[0].query, "fabric-api")

    def test_wrong_loader_diagnosis_requires_manual_review(self):
        from mythweaver.runtime.contracts import RuntimeDiagnosis
        from mythweaver.runtime.repair_actions import actions_for_diagnoses

        actions = actions_for_diagnoses(
            [
                RuntimeDiagnosis(
                    kind="wrong_loader",
                    confidence="high",
                    summary="Requires Forge",
                    evidence=["requires forge"],
                    suggested_repair_action_kinds=["manual_review"],
                )
            ]
        )

        self.assertEqual(actions[0].action, "manual_review")
        self.assertEqual(actions[0].safety, "manual")


if __name__ == "__main__":
    unittest.main()
