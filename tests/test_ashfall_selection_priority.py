import unittest

from tests.test_scoring import candidate


def ashfall_profile(**updates):
    from mythweaver.schemas.contracts import RequirementProfile

    data = {
        "name": "Ashfall Frontier",
        "search_keywords": [
            "volcanic",
            "basalt",
            "lava caves",
            "mountains",
            "ruins",
            "structures",
            "dungeons",
            "temples",
            "abandoned mines",
            "villages",
            "caves",
            "exploration",
            "survival",
            "performance",
            "shader",
        ],
        "required_capabilities": [
            "caves",
            "structures",
            "ruins",
            "dungeons",
            "exploration",
            "performance_foundation",
            "shader_support",
        ],
        "preferred_capabilities": [
            "volcanic_worldgen",
            "mountains",
            "lava_caves",
            "basalt_biomes",
            "abandoned_mines",
            "temples",
            "villages",
            "hostile_mobs",
            "survival_progression",
            "atmosphere",
            "ambient_sounds",
            "waystones",
            "maps",
        ],
        "foundation_policy": {"performance": "enabled", "shaders": "enabled", "utilities": "enabled"},
        "max_selected_before_dependencies": 35,
    }
    data.update(updates)
    return RequirementProfile.model_validate(data)


def prepared(candidates, profile):
    from mythweaver.catalog.scoring import score_candidates
    from mythweaver.pipeline.sanitizer import sanitize_candidates_for_profile

    sanitized = sanitize_candidates_for_profile(candidates, profile, strict_profile_mode=True)
    return score_candidates(sanitized.candidates, profile)


class AshfallSelectionPriorityTests(unittest.TestCase):
    def test_required_capabilities_are_prioritized_before_lava_novelty(self):
        from mythweaver.pipeline.selection import select_candidates

        profile = ashfall_profile(required_capabilities=["ruins", "exploration", "structures"])
        ruins = candidate("ruins", "Ashen Ruins", "Ruins, abandoned temples, and frontier structures.")
        exploration = candidate("explore", "Frontier Explorer", "Exploration maps and discovery for harsh frontier travel.")
        novelty = candidate("lava-disc", "Lava Chicken Disc", "A funny lava chicken music disc single item.")

        selection = select_candidates(prepared([novelty, ruins, exploration], profile), max_mods=2, profile=profile, strict_profile_mode=True)

        self.assertEqual(set(selection.selected_project_ids), {"ruins", "explore"})
        self.assertIn("lava-disc", [rejection.project_id for rejection in selection.rejected_mods])

    def test_lava_novelty_mods_are_penalized_in_strict_mode(self):
        from mythweaver.pipeline.selection import select_candidates

        profile = ashfall_profile(required_capabilities=["structures", "dungeons", "exploration"])
        mods = [
            candidate("lava-disc", "Lava Chicken Disc", "Funny lava chicken music disc single item."),
            candidate("hot-chicken", "Hot Lava Chicken", "Joke food item with lava chicken."),
            candidate("wda", "When Dungeons Arise", "Large dungeons, towers, temples, structures, and exploration."),
            candidate("mineshafts", "Better Mineshafts", "Abandoned mines, ruins, structures, and exploration."),
        ]

        selection = select_candidates(prepared(mods, profile), max_mods=3, profile=profile, strict_profile_mode=True)

        self.assertIn("wda", selection.selected_project_ids)
        self.assertIn("mineshafts", selection.selected_project_ids)
        self.assertNotIn("lava-disc", selection.selected_project_ids)
        self.assertTrue(any(rejection.reason == "novelty_penalty_applied" for rejection in selection.rejected_mods))

    def test_performance_foundation_minimum_requires_more_than_iris(self):
        from mythweaver.pipeline.selection import select_candidates

        profile = ashfall_profile(required_capabilities=["performance_foundation", "shader_support"])
        iris = candidate("iris", "Iris Shaders", "Shader support for Fabric.")
        only_iris = select_candidates(prepared([iris], profile), max_mods=5, profile=profile, strict_profile_mode=True)

        self.assertEqual(only_iris.selected_project_ids, ["iris"])
        self.assertIn("shader_support", only_iris.pillar_coverage["atmosphere_visuals"]["capabilities"])
        self.assertFalse(only_iris.pillar_coverage["performance_foundation"]["satisfied"])
        self.assertTrue(only_iris.performance_foundation_gaps)

        sodium = candidate("sodium", "Sodium", "Renderer optimization and performance.")
        lithium = candidate("lithium", "Lithium", "Game logic optimization.")
        ferrite = candidate("ferritecore", "FerriteCore", "Memory optimization.")
        culling = candidate("entityculling", "EntityCulling", "Entity culling optimization.")
        full = select_candidates(
            prepared([iris, sodium, lithium, ferrite, culling], profile),
            max_mods=8,
            profile=profile,
            strict_profile_mode=True,
        )

        self.assertFalse(full.performance_foundation_gaps)
        self.assertTrue(full.pillar_coverage["performance_foundation"]["satisfied"])

    def test_pillar_coverage_report_contains_ashfall_pillars(self):
        from mythweaver.pipeline.selection import select_candidates

        profile = ashfall_profile()
        selection = select_candidates(prepared([], profile), max_mods=5, profile=profile, strict_profile_mode=True)

        for pillar in (
            "volcanic_worldgen",
            "ruins_structures",
            "exploration_dungeons",
            "villages_frontier",
            "atmosphere_visuals",
            "performance_foundation",
        ):
            self.assertIn(pillar, selection.pillar_coverage)

    def test_quality_gate_top_blockers_and_actions_for_missing_required_and_novelty(self):
        from mythweaver.pipeline.service import _next_actions, _quality_gate_diagnostics, _selection_quality_gate
        from mythweaver.schemas.contracts import CandidateSelection, PerformanceFoundationReport

        profile = ashfall_profile(required_capabilities=["ruins", "exploration", "performance_foundation"])
        novelty = candidate("lava-disc", "Lava Chicken Disc", "Funny lava chicken music disc single item.")
        selection = CandidateSelection(
            selected_project_ids=["lava-disc"],
            novelty_mods_selected=["lava-disc"],
            performance_foundation_gaps=["renderer_optimization", "logic_optimization"],
            pillar_coverage={
                "ruins_structures": {"required": True, "satisfied": False},
                "exploration_dungeons": {"required": True, "satisfied": False},
                "performance_foundation": {"required": True, "satisfied": False},
            },
        )

        diagnostics = _quality_gate_diagnostics(profile, [novelty], [], strict_profile_mode=True, selection=selection)
        failures = _selection_quality_gate(profile, [novelty], [], max_before_dependencies=5, strict_profile_mode=True, selection=selection)
        actions = _next_actions("failed", PerformanceFoundationReport(), [], failed_stage="selection_quality_gate", diagnostics=diagnostics)

        self.assertTrue(failures)
        self.assertTrue(any("Missing required capability: ruins" == blocker for blocker in diagnostics["top_blockers"]))
        self.assertTrue(any("Missing required capability: exploration" == blocker for blocker in diagnostics["top_blockers"]))
        self.assertIn("search_more_for_ruins_structures", actions)
        self.assertIn("search_more_for_exploration_dungeons", actions)
        self.assertIn("reduce_lava_novelty_candidates", actions)
        self.assertNotIn("run_full_build", actions)

    def test_search_strategy_includes_required_pillar_terms(self):
        from mythweaver.pipeline.strategy import build_search_strategy

        profile = ashfall_profile()
        queries = " ".join(plan.query for plan in build_search_strategy(profile, limit=35).search_plans)

        for term in ("ruins", "structures", "dungeons", "temples", "abandoned mines", "caves", "exploration", "volcanic", "performance", "shader"):
            self.assertIn(term, queries)


if __name__ == "__main__":
    unittest.main()
