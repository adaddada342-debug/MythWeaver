import io
import unittest
from contextlib import redirect_stderr, redirect_stdout


class CliStartTests(unittest.TestCase):
    def test_start_command_prints_premade_message(self):
        from mythweaver.cli.main import main

        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["start"])

        self.assertEqual(exit_code, 0)
        self.assertIn("State your modpack idea.", output.getvalue())

    def test_generate_without_prompt_or_profile_exits_cleanly(self):
        from mythweaver.cli.main import main

        error = io.StringIO()
        with redirect_stderr(error):
            with self.assertRaises(SystemExit) as raised:
                main(["generate"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("provide a prompt or --profile", error.getvalue())


if __name__ == "__main__":
    unittest.main()
