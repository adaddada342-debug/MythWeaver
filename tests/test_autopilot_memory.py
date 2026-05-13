import unittest


class AutopilotMemoryTests(unittest.TestCase):
    def test_repeated_issue_after_same_action_is_detected(self):
        from mythweaver.autopilot.memory import AutopilotMemory
        from mythweaver.runtime.contracts import RuntimeAction, RuntimeIssue

        memory = AutopilotMemory()
        issue = RuntimeIssue(kind="missing_dependency", severity="fatal", confidence=0.9, message="Missing fabric-api", evidence=[], missing_mods=["fabric-api"])
        action = RuntimeAction(action="add_mod", safety="safe", reason="add dependency", query="fabric-api")

        memory.record_attempt(["1.20.1", "fabric"], [issue], [action])
        memory.record_attempt(["1.20.1", "fabric"], [issue], [action])

        self.assertTrue(memory.repeated_after_same_action(issue, action))


if __name__ == "__main__":
    unittest.main()
