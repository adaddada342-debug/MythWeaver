import unittest


class CrashAnalyzerTests(unittest.TestCase):
    def test_classifies_missing_dependency(self):
        from mythweaver.validation.crash_analyzer import analyze_failure

        report = analyze_failure(
            "Mod resolution failed\n"
            "Mod fabric-api requires fabricloader >=0.15.0\n"
            "Install fabric-api or a compatible dependency."
        )

        self.assertEqual(report.classification, "missing_dependency")
        self.assertTrue(report.repair_candidates)

    def test_classifies_mixin_failure(self):
        from mythweaver.validation.crash_analyzer import analyze_failure

        report = analyze_failure("Mixin apply failed for mod sodium at net.minecraft.client.Renderer")

        self.assertEqual(report.classification, "mixin_failure")


if __name__ == "__main__":
    unittest.main()
