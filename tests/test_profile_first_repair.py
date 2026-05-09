import unittest
from pathlib import Path

from tests.test_pipeline_discovery import version_payload
from tests.test_scoring import candidate


SUN_PROFILE = {
    "name": "The Sun Forgot Us",
    "summary": "Cold dying-sun survival.",
    "themes": ["dying sun", "cold apocalypse", "long nights", "frozen ruins", "village defense"],
    "search_keywords": [
        "winter",
        "cold",
        "frozen",
        "darkness",
        "undead",
        "ruins",
        "structures",
        "villages",
        "temperature",
        "survival",
        "atmosphere",
        "shader",
        "performance",
    ],
    "negative_keywords": ["desert", "outback", "badlands", "tropical", "heat survival"],
    "required_capabilities": [
        "cold_survival",
        "structures",
        "undead",
        "performance_foundation",
        "shader_support",
    ],
    "preferred_capabilities": ["village_defense", "atmosphere", "dungeons"],
    "forbidden_capabilities": ["desert_worldgen", "outback", "tropical_worldgen"],
    "explicit_exclusions": ["desert", "outback", "badlands"],
    "foundation_policy": {"performance": "enabled", "shaders": "enabled", "utilities": "enabled"},
    "max_selected_before_dependencies": 35,
}


class ProfileFirstRepairTests(unittest.TestCase):
    def test_profile_first_search_uses_explicit_terms_and_blocks_exclusions(self):
        from mythweaver.catalog.scoring import score_candidates
        from mythweaver.pipeline.strategy import build_search_strategy
        from mythweaver.schemas.contracts import RequirementProfile

        profile = RequirementProfile.model_validate(SUN_PROFILE)
        strategy = build_search_strategy(profile, limit=35)
        queries = [plan.query for plan in strategy.search_plans]
        query_text = " ".join(queries)

        for term in ("winter", "cold", "darkness", "undead", "structures", "temperature"):
            self.assertIn(term, queries)
        for term in ("desert", "outback", "badlands"):
            self.assertNotIn(term, query_text)
        self.assertEqual(strategy.search_plans[0].source_field, "search_keywords")
        self.assertGreater(strategy.search_plans[0].weight, strategy.search_plans[-1].weight)

        bad = candidate("badlands-biomes", "Badlands Biomes", "Desert outback badlands worldgen.")
        cold = candidate("frost", "Frozen Structures", "Cold winter undead ruins and structures.")
        scored = score_candidates([bad, cold], profile)

        self.assertEqual(scored[0].project_id, "frost")
        self.assertEqual(scored[-1].score.hard_reject_reason, "explicit_exclusion")

    def test_raw_prompt_the_sun_forgot_us_does_not_infer_desert_terms(self):
        from mythweaver.pipeline.profile import profile_from_prompt
        from mythweaver.pipeline.strategy import build_search_strategy

        profile = profile_from_prompt(
            "The Sun Forgot Us: a dying sun cold survival pack with long nights and frozen villages"
        )
        self.assertTrue({"cold apocalypse", "dying sun", "long nights"} & set(profile.themes))
        self.assertIn("darkness", profile.mood)
        self.assertFalse({"desert", "outback", "badlands"} & set(profile.terrain + profile.themes))

        strategy = build_search_strategy(profile)
        query_text = " ".join(plan.query for plan in strategy.search_plans)
        for term in ("desert", "outback", "badlands"):
            self.assertNotIn(term, query_text)

    def test_outback_zombie_apocalypse_still_includes_arid_terms(self):
        from mythweaver.pipeline.profile import profile_from_prompt
        from mythweaver.pipeline.strategy import build_search_strategy

        profile = profile_from_prompt(
            "Australian outback zombie apocalypse with desert heat ruins scarcity"
        )
        strategy = build_search_strategy(profile)
        query_text = " ".join(plan.query for plan in strategy.search_plans)

        for term in ("outback", "desert", "zombie", "ruins", "scarcity"):
            self.assertIn(term, query_text)

    def test_conflicting_profile_fails_validation(self):
        from pydantic import ValidationError

        from mythweaver.schemas.contracts import RequirementProfile

        with self.assertRaisesRegex(ValidationError, "shader_support requires foundation_policy.shaders"):
            RequirementProfile(
                name="Contradiction",
                required_capabilities=["shader_support"],
                foundation_policy={"shaders": "disabled"},
            )

    def test_confidence_penalizes_explicit_exclusion_violations(self):
        from mythweaver.pipeline.service import _confidence_scores
        from mythweaver.schemas.contracts import RequirementProfile

        profile = RequirementProfile(
            name="Cold",
            explicit_exclusions=["desert"],
            required_capabilities=["cold_survival"],
        )
        selected = [
            candidate("desert", "Desert Heat", "Desert heat survival."),
            candidate("cold", "Cold Nights", "Cold survival temperature."),
        ]

        confidence = _confidence_scores(status="completed", selected_mods=selected, profile=profile)

        self.assertLess(confidence.theme_match, 0.6)
        self.assertLess(confidence.pack_coherence, 0.6)

    def test_stage_aware_next_actions_for_dependency_resolution(self):
        from mythweaver.pipeline.service import _next_actions
        from mythweaver.schemas.contracts import PerformanceFoundationReport

        actions = _next_actions("failed", PerformanceFoundationReport(), [], failed_stage="dependency_resolution")

        self.assertIn("inspect_unresolved_dependencies", actions)
        self.assertIn("rerun_dry_run", actions)
        self.assertNotIn("run_full_build", actions)


class DependencyHydrationRepairTests(unittest.IsolatedAsyncioTestCase):
    async def test_dependency_id_is_hydrated_and_marked_dependency_added(self):
        from mythweaver.pipeline.dependencies import expand_required_dependencies
        from mythweaver.schemas.contracts import DependencyRecord, RequirementProfile

        class HydratingModrinth:
            async def get_project(self, project_id_or_slug):
                self.requested_project = project_id_or_slug
                return {
                    "id": "fabric-api",
                    "project_id": "fabric-api",
                    "slug": "fabric-api",
                    "title": "Fabric API",
                    "description": "Core Fabric library.",
                    "categories": ["library"],
                    "client_side": "required",
                    "server_side": "required",
                    "downloads": 100,
                    "follows": 10,
                    "versions": ["1.20.1"],
                }

            async def list_project_versions(self, project_id_or_slug, *, loader, minecraft_version, include_changelog=False):
                return [version_payload("fabric-api", game_versions=[minecraft_version])]

        main = candidate("main", "Main", "Requires Fabric API")
        main.selected_version.dependencies.append(
            DependencyRecord(project_id="fabric-api", dependency_type="required")
        )
        expanded, rejected = await expand_required_dependencies(
            HydratingModrinth(),
            [main],
            RequirementProfile(name="Dependency Pack", themes=["utility"], minecraft_version="1.20.1"),
            "1.20.1",
        )

        dependency = next(mod for mod in expanded if mod.project_id == "fabric-api")
        self.assertEqual(dependency.title, "Fabric API")
        self.assertEqual(dependency.selection_type, "dependency_added")
        self.assertEqual(rejected, [])


class SelectionGateRepairTests(unittest.IsolatedAsyncioTestCase):
    async def test_selection_quality_gate_fails_before_dependency_resolution(self):
        from mythweaver.pipeline.service import GenerationPipeline
        from mythweaver.schemas.contracts import GenerationRequest, RequirementProfile
        from tests.test_pipeline_generation import FakeFacade

        class BadModrinth:
            async def search_projects(self, plan):
                return {
                    "hits": [
                        {
                            "project_id": f"{plan.query}-desert",
                            "slug": f"{plan.query}-desert",
                            "title": "Desert Placeholder",
                            "description": "Desert outback badlands placeholder.",
                            "categories": ["worldgen"],
                            "client_side": "required",
                            "server_side": "optional",
                            "downloads": 1,
                            "follows": 0,
                            "versions": ["1.20.1"],
                        }
                    ]
                }

            async def list_project_versions(self, project_id_or_slug, *, loader, minecraft_version, include_changelog=False):
                return [version_payload(project_id_or_slug, game_versions=["1.20.1"])]

        class GateFacade(FakeFacade):
            def __init__(self, output_dir):
                super().__init__(output_dir)
                self.modrinth = BadModrinth()
                self.resolve_called = False

            def resolve_dependencies(self, *args, **kwargs):
                self.resolve_called = True
                return super().resolve_dependencies(*args, **kwargs)

        output_dir = Path.cwd() / "output" / "test-selection-quality-gate"
        facade = GateFacade(output_dir)
        pipeline = GenerationPipeline(facade)
        profile = RequirementProfile(
            name="Gate",
            search_keywords=["winter", "cold"],
            explicit_exclusions=["desert", "outback", "badlands"],
            required_capabilities=["cold_survival"],
            max_selected_before_dependencies=5,
        )

        report = await pipeline.generate(
            GenerationRequest(profile=profile, output_dir=str(output_dir), dry_run=True)
        )

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.failed_stage, "selection_quality_gate")
        self.assertFalse(facade.resolve_called)
        self.assertNotIn("run_full_build", report.next_actions)


if __name__ == "__main__":
    unittest.main()
