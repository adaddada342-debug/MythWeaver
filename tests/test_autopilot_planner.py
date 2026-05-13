import unittest


class AutopilotPlannerTests(unittest.TestCase):
    def test_planner_prefers_safe_missing_dependency_addition(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.memory import AutopilotMemory
        from mythweaver.autopilot.planner import plan_runtime_repairs
        from mythweaver.runtime.contracts import RuntimeIssue, RuntimeLaunchReport

        report = RuntimeLaunchReport(
            status="failed",
            stage="classify",
            instance_path=None,
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version=None,
            java_path=None,
            command_preview=[],
            exit_code=1,
            success_signal=None,
            issues=[RuntimeIssue(kind="missing_dependency", severity="fatal", confidence=0.9, message="Missing fabric-api", evidence=[], missing_mods=["fabric-api"])],
            recommended_next_actions=[],
            logs_scanned=[],
            warnings=[],
        )

        actions = plan_runtime_repairs(report, AutopilotRequest(selected_mods_path="selected_mods.json", sources=["modrinth"]), AutopilotMemory())

        self.assertEqual(actions[0].action, "add_mod")
        self.assertEqual(actions[0].safety, "safe")

    def test_planner_blocks_dangerous_actions(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.memory import AutopilotMemory
        from mythweaver.autopilot.planner import filter_applicable_actions
        from mythweaver.runtime.contracts import RuntimeAction

        actions = filter_applicable_actions(
            [
                RuntimeAction(action="add_mod", safety="dangerous", reason="direct URL", query="https://example.invalid/mod.jar"),
                RuntimeAction(action="manual_review", safety="manual", reason="unknown"),
            ],
            AutopilotRequest(selected_mods_path="selected_mods.json", sources=["modrinth"]),
            AutopilotMemory(),
        )

        self.assertEqual(actions, [])

    def test_target_matrix_rerun_is_blocked_when_switching_disabled(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.memory import AutopilotMemory
        from mythweaver.autopilot.planner import filter_applicable_actions
        from mythweaver.runtime.contracts import RuntimeAction

        actions = filter_applicable_actions(
            [RuntimeAction(action="rerun_target_matrix", safety="safe", reason="wrong target")],
            AutopilotRequest(selected_mods_path="selected_mods.json", sources=["modrinth"], allow_target_switch=False),
            AutopilotMemory(),
        )

        self.assertEqual(actions, [])


if __name__ == "__main__":
    unittest.main()
