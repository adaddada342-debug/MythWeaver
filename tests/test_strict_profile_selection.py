import unittest

from tests.test_scoring import candidate


def forest_profile(**updates):
    from mythweaver.schemas.contracts import RequirementProfile

    data = {
        "name": "The World Beneath the Roots",
        "themes": ["ancient forest mystery", "overgrown apocalypse", "nature reclaiming civilization"],
        "search_keywords": [
            "forest",
            "overgrown",
            "roots",
            "moss",
            "mushrooms",
            "fungal",
            "caves",
            "underground",
            "ruins",
            "structures",
            "dungeons",
            "villages",
            "atmosphere",
            "performance",
            "shader",
        ],
        "negative_keywords": [
            "modern city",
            "transit",
            "train",
            "railway",
            "metro",
            "london underground",
            "mtr",
            "create",
            "automation",
            "industrial",
            "machinery",
            "factory",
            "wallpaper",
            "overlay",
            "windows",
            "guns",
            "vehicles",
            "space",
            "nuclear",
            "sci-fi",
            "desert",
            "outback",
        ],
        "required_capabilities": [
            "forest_worldgen",
            "structures",
            "ruins",
            "caves",
            "exploration",
            "performance_foundation",
            "shader_support",
        ],
        "preferred_capabilities": [
            "overgrown_nature",
            "moss",
            "roots",
            "mushroom_biomes",
            "underground_biomes",
            "nature_magic",
            "village_expansion",
            "dungeons",
            "atmosphere",
            "ambient_sounds",
            "waystones",
            "maps",
            "survival_progression",
        ],
        "forbidden_capabilities": [
            "modern_transit",
            "trains",
            "vehicles",
            "industrial_automation",
            "modern_ui_overlay",
            "wallpaper_cosmetic",
            "guns",
            "space",
            "desert_worldgen",
        ],
        "explicit_exclusions": ["modern city", "transit", "industrial", "desert", "outback"],
        "theme_anchors": ["ancient forest", "overgrown ruins", "root kingdoms"],
        "worldgen_anchors": ["massive forests", "root-covered temples", "buried ruins", "fungal caverns"],
        "gameplay_anchors": ["exploration first progression", "village survival pockets"],
        "foundation_policy": {"performance": "enabled", "shaders": "enabled", "utilities": "enabled"},
        "max_selected_before_dependencies": 35,
    }
    data.update(updates)
    return RequirementProfile.model_validate(data)


class StrictProfileSelectionTests(unittest.TestCase):
    def test_forest_profile_rejects_modern_transit_before_selection(self):
        from mythweaver.pipeline.sanitizer import sanitize_candidates_for_profile

        profile = forest_profile()
        bad = candidate("mtr-london", "MTR London Underground Addon", "Metro trains and railway stations.")

        result = sanitize_candidates_for_profile([bad], profile, strict_profile_mode=True)

        self.assertEqual(result.candidates, [])
        self.assertEqual(result.rejected[0].project_id, "mtr-london")
        self.assertIn(result.rejected[0].reason, {"forbidden_capability_match", "domain_blocklist_match", "transit_vehicle_rejected"})
        self.assertIn("modern_transit", result.rejected[0].detail)

    def test_forest_profile_rejects_industrial_automation_unless_requested(self):
        from mythweaver.pipeline.sanitizer import sanitize_candidates_for_profile

        bad = candidate("create-features", "Additional Create Features", "Automation machinery and factory addons.")

        rejected = sanitize_candidates_for_profile([bad], forest_profile(), strict_profile_mode=True)
        self.assertEqual(rejected.candidates, [])
        self.assertEqual(rejected.rejected[0].reason, "industrial_automation_rejected")

        allowed_profile = forest_profile(
            negative_keywords=["modern city"],
            forbidden_capabilities=["modern_transit"],
            explicit_exclusions=["modern city"],
            preferred_capabilities=["industrial_automation"],
            search_keywords=["create", "automation", "forest"],
        )
        accepted = sanitize_candidates_for_profile([bad], allowed_profile, strict_profile_mode=True)
        self.assertEqual([mod.project_id for mod in accepted.candidates], ["create-features"])

    def test_forest_profile_rejects_ui_cosmetic_junk(self):
        from mythweaver.pipeline.sanitizer import sanitize_candidates_for_profile

        profile = forest_profile()
        junk = [
            candidate("windows-starting-overlay", "WindowsStartingOverlay", "Windows start menu overlay."),
            candidate("wallpaper", "Wallpaper", "Adds wallpaper cosmetic blocks."),
        ]

        result = sanitize_candidates_for_profile(junk, profile, strict_profile_mode=True)

        self.assertEqual(result.candidates, [])
        self.assertEqual({rejection.reason for rejection in result.rejected}, {"ui_wallpaper_overlay_rejected"})

    def test_forest_profile_accepts_relevant_mods_with_theme_evidence(self):
        from mythweaver.pipeline.sanitizer import sanitize_candidates_for_profile

        profile = forest_profile()
        relevant = [
            candidate("surface-mushrooms", "Surface Mushrooms", "Adds mushroom and fungal forest biomes."),
            candidate("biome-moss", "Biome Moss", "Moss and overgrown nature for biomes."),
            candidate("moss-layers", "Moss Layers", "Layered moss carpets and roots."),
            candidate("wda", "When Dungeons Arise", "Large dungeons, towers, temples, and structures for exploration."),
        ]

        result = sanitize_candidates_for_profile(relevant, profile, strict_profile_mode=True)

        self.assertEqual({mod.project_id for mod in result.candidates}, {mod.project_id for mod in relevant})
        self.assertTrue(all(mod.matched_capabilities for mod in result.candidates))
        self.assertTrue(all(mod.matched_profile_terms for mod in result.candidates))

    def test_strict_profile_requires_positive_evidence_for_theme_mods(self):
        from mythweaver.pipeline.sanitizer import sanitize_candidates_for_profile

        generic = candidate("generic-ui", "Convenience Buttons", "Generic utility controls.", categories=["utility"])

        result = sanitize_candidates_for_profile([generic], forest_profile(), strict_profile_mode=True)

        self.assertEqual(result.candidates, [])
        self.assertEqual(result.rejected[0].reason, "low_theme_relevance")

    def test_quality_gate_diagnostics_explain_pollution(self):
        from mythweaver.pipeline.service import _confidence_scores, _quality_gate_diagnostics

        profile = forest_profile()
        bad = candidate("wallpaper", "Wallpaper", "Adds wallpaper cosmetic blocks.")
        good = candidate("biome-moss", "Biome Moss", "Moss and overgrown nature for biomes.")

        diagnostics = _quality_gate_diagnostics(profile, [bad, good], [], strict_profile_mode=True)

        self.assertIn("off_theme_selected_mods", diagnostics)
        self.assertIn("explicit_exclusion_violations", diagnostics)
        self.assertIn("low_evidence_selected_mods", diagnostics)
        self.assertIn("selected_mod_budget_breakdown", diagnostics)
        self.assertIn("wallpaper", diagnostics["off_theme_selected_mods"])

        confidence = _confidence_scores(
            status="completed",
            selected_mods=[bad, good],
            profile=profile,
            quality_diagnostics=diagnostics,
        )
        self.assertLess(confidence.theme_match, 0.6)

    def test_search_plan_for_roots_profile_includes_forest_terms_and_blocks_modern_terms(self):
        from mythweaver.pipeline.strategy import build_search_strategy

        profile = forest_profile()
        queries = [plan.query for plan in build_search_strategy(profile, limit=35).search_plans]
        query_text = " ".join(queries)

        for term in ("forest", "overgrown", "roots", "moss", "mushrooms", "caves", "underground", "ruins", "structures", "dungeons", "villages", "atmosphere", "performance", "shader"):
            self.assertIn(term, query_text)
        for blocked in ("train", "railway", "metro", "industrial", "create", "wallpaper", "windows", "desert", "outback"):
            self.assertNotIn(blocked, query_text)


if __name__ == "__main__":
    unittest.main()
