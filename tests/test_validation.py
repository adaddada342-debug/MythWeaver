import unittest


class ValidationTests(unittest.TestCase):
    def test_prism_launch_validation_skips_when_unconfigured(self):
        from mythweaver.core.settings import Settings
        from mythweaver.validation.prism import validate_launch

        report = validate_launch("missing-instance", Settings(prism_path=None, prism_root=None))

        self.assertEqual(report.status, "skipped")
        self.assertIn("Prism", report.details)


if __name__ == "__main__":
    unittest.main()
