import unittest
from pathlib import Path


class OnboardingTests(unittest.TestCase):
    def test_start_message_is_simple_and_user_facing(self):
        from mythweaver.onboarding import START_MESSAGE

        self.assertEqual(START_MESSAGE, "State your modpack idea.")

    def test_agent_prompt_contains_real_workflow_and_no_ai_requirement(self):
        from mythweaver.onboarding import build_agent_prompt

        prompt = build_agent_prompt("infinite winter survival")

        self.assertIn("infinite winter survival", prompt)
        self.assertIn("RequirementProfile", prompt)
        self.assertIn("search_modrinth", prompt)
        self.assertIn("build_pack", prompt)
        self.assertIn("Do not invent Modrinth projects", prompt)
        self.assertIn("No internal MythWeaver AI provider is required", prompt)

    def test_session_files_are_written_for_agents(self):
        from mythweaver.onboarding import write_agent_session

        root = Path.cwd() / "output" / "test-onboarding"
        artifact = write_agent_session("cozy dragons", root)

        self.assertEqual(artifact.kind, "agent-session")
        self.assertTrue((root / "modpack_request.txt").is_file())
        self.assertTrue((root / "agent_next_steps.md").is_file())
        self.assertIn("cozy dragons", (root / "agent_next_steps.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
