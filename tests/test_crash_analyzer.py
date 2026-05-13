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

    def test_classifies_mass_incompatibility_as_final_artifact_invalid(self):
        from mythweaver.validation.crash_analyzer import analyze_failure

        report = analyze_failure(
            "Incompatible mods found!\n"
            "Some of your mods are incompatible with each other or with Minecraft.\n"
            "Try removing some of the mods listed below."
        )
        self.assertEqual(report.classification, "final_artifact_invalid")
        self.assertIn("duplicate_mod_ids", report.likely_causes)


if __name__ == "__main__":
    unittest.main()
