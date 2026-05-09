import unittest


class PathSafetyTests(unittest.TestCase):
    def test_safe_filename_rejects_nested_and_absolute_paths(self):
        from mythweaver.builders.paths import safe_file_name

        self.assertEqual(safe_file_name("mod.jar"), "mod.jar")

        for value in ("../mod.jar", "mods/mod.jar", "/mod.jar", "C:/mod.jar", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    safe_file_name(value)


if __name__ == "__main__":
    unittest.main()
