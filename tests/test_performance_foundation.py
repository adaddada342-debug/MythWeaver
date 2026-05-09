import unittest


class PerformanceFoundationPolicyTests(unittest.TestCase):
    def test_default_policy_enables_performance_and_shader_support(self):
        from mythweaver.pipeline.performance import build_performance_foundation_plan
        from mythweaver.pipeline.profile import profile_from_prompt

        profile = profile_from_prompt("cinematic zombie survival in ruined desert towns")
        plan = build_performance_foundation_plan(profile)

        self.assertTrue(plan.performance_enabled)
        self.assertTrue(plan.shader_support_enabled)
        self.assertTrue(plan.targets)
        self.assertTrue(any(target.capability == "renderer_optimization" for target in plan.targets))
        self.assertTrue(any(target.capability == "shader_support" for target in plan.targets))

    def test_opt_out_disables_auto_performance_and_shader_support(self):
        from mythweaver.pipeline.performance import build_performance_foundation_plan
        from mythweaver.pipeline.profile import profile_from_prompt

        profile = profile_from_prompt("Make me a vanilla-style zombie pack with no performance mods and no shaders")
        plan = build_performance_foundation_plan(profile)

        self.assertFalse(plan.performance_enabled)
        self.assertFalse(plan.shader_support_enabled)
        self.assertFalse(plan.targets)

    def test_loader_aware_capabilities_are_not_fabric_name_only(self):
        from mythweaver.pipeline.performance import FOUNDATION_CAPABILITIES

        self.assertIn("fabric", FOUNDATION_CAPABILITIES)
        self.assertIn("forge", FOUNDATION_CAPABILITIES)
        self.assertIn("neoforge", FOUNDATION_CAPABILITIES)
        self.assertIn("renderer_optimization", FOUNDATION_CAPABILITIES["fabric"])
        self.assertIn("shader_support", FOUNDATION_CAPABILITIES["fabric"])

    def test_shader_recommendations_match_apocalyptic_dusty_prompt(self):
        from mythweaver.pipeline.performance import build_performance_foundation_plan
        from mythweaver.pipeline.profile import profile_from_prompt

        profile = profile_from_prompt(
            "Australian outback post apocalyptic zombie survival with ruined towns harsh heat scarce resources cinematic atmosphere"
        )
        plan = build_performance_foundation_plan(profile)

        self.assertEqual(plan.shader_recommendations.primary.category, "apocalyptic_dusty")
        self.assertFalse(plan.shader_recommendations.installed)
        self.assertTrue(plan.shader_recommendations.low_end_fallback)


if __name__ == "__main__":
    unittest.main()
