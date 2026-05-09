import unittest


class PipelineStrategyTests(unittest.TestCase):
    def test_search_strategy_generates_multiple_fabric_mod_searches(self):
        from mythweaver.pipeline.profile import profile_from_prompt
        from mythweaver.pipeline.strategy import build_search_strategy

        profile = profile_from_prompt("dark winter survival with structures and weather")
        strategy = build_search_strategy(profile, limit=12)

        self.assertGreaterEqual(len(strategy.search_plans), 4)
        self.assertLessEqual(len(strategy.search_plans), 32)
        self.assertTrue(all(plan.loader == "fabric" for plan in strategy.search_plans))
        self.assertTrue(all(plan.project_type == "mod" for plan in strategy.search_plans))
        self.assertTrue(any("winter" in plan.query for plan in strategy.search_plans))

    def test_outback_apocalypse_strategy_includes_theme_and_foundation_terms(self):
        from mythweaver.pipeline.profile import profile_from_prompt
        from mythweaver.pipeline.strategy import build_search_strategy

        profile = profile_from_prompt(
            "Australian outback post apocalyptic zombie survival with ruined towns harsh heat scarce resources cinematic atmosphere"
        )
        strategy = build_search_strategy(profile, limit=12)
        queries = {plan.query for plan in strategy.search_plans}
        query_text = " ".join(sorted(queries))

        self.assertIn("zombie", query_text)
        self.assertTrue("apocalypse" in query_text or "wasteland" in query_text)
        self.assertTrue("desert" in query_text or "outback" in query_text or "badlands" in query_text)
        self.assertTrue("ruins" in query_text or "structures" in query_text)
        self.assertTrue("survival" in query_text or "scarcity" in query_text)
        self.assertTrue("performance" in query_text or "optimization" in query_text)
        self.assertTrue("shader" in query_text or "atmosphere" in query_text)


if __name__ == "__main__":
    unittest.main()
