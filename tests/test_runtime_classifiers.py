import unittest


class RuntimeClassifierTests(unittest.TestCase):
    def test_missing_dependency_is_structured_with_evidence(self):
        from mythweaver.runtime.classifiers import classify_runtime_text

        issues = classify_runtime_text("ModResolutionException: mod cameraoverhaul requires mod fabric-api")

        self.assertEqual(issues[0].kind, "missing_dependency")
        self.assertIn("fabric-api", issues[0].missing_mods)
        self.assertTrue(issues[0].evidence)

    def test_timeout_issue_is_explicit(self):
        from mythweaver.runtime.classifiers import timeout_issue

        issue = timeout_issue(180)

        self.assertEqual(issue.kind, "timeout")
        self.assertEqual(issue.severity, "fatal")

    def test_mixin_failure_is_not_autorepaired_as_dependency(self):
        from mythweaver.runtime.classifiers import classify_runtime_text

        issues = classify_runtime_text("Mixin apply failed: InvalidMixinException in renderer")

        self.assertEqual(issues[0].kind, "mixin_failure")
        self.assertEqual(issues[0].suspected_mods, [])


if __name__ == "__main__":
    unittest.main()
