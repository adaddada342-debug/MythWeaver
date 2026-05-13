import unittest
from unittest.mock import patch


class RuntimeJavaTests(unittest.TestCase):
    def test_required_java_for_minecraft_versions(self):
        from mythweaver.runtime.java import required_java_for_minecraft

        self.assertEqual(required_java_for_minecraft("1.21.1"), 21)
        self.assertEqual(required_java_for_minecraft("1.20.5"), 21)
        self.assertEqual(required_java_for_minecraft("1.20.4"), 17)
        self.assertEqual(required_java_for_minecraft("1.18.2"), 17)
        self.assertEqual(required_java_for_minecraft("1.17.1"), 16)
        self.assertEqual(required_java_for_minecraft("1.16.5"), 8)

    def test_choose_java_reports_missing_actionable_issue(self):
        from mythweaver.runtime.java import choose_java

        with patch("mythweaver.runtime.java.detect_java_candidates", return_value=[]):
            choice = choose_java("1.20.1")

        self.assertIsNone(choice.java_path)
        self.assertEqual(choice.issue.kind, "java_version_mismatch")
        self.assertIn("Java 17", choice.issue.message)

    def test_choose_java_accepts_compatible_explicit_java(self):
        from mythweaver.runtime.java import choose_java

        with patch("mythweaver.runtime.java.get_java_major_version", return_value=17):
            choice = choose_java("1.20.1", explicit_java_path="C:/Java/bin/java.exe")

        self.assertEqual(choice.java_path, "C:/Java/bin/java.exe")
        self.assertEqual(choice.major_version, 17)
        self.assertIsNone(choice.issue)


if __name__ == "__main__":
    unittest.main()
