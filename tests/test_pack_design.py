import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


class PackDesignTests(unittest.TestCase):
    def test_cli_help_includes_design_pack(self):
        from mythweaver.cli.main import _fallback_main

        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            _fallback_main(["design-pack", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Design a deterministic modpack blueprint", stdout.getvalue())

    def test_cli_help_includes_review_design(self):
        from mythweaver.cli.main import _fallback_main

        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            _fallback_main(["review-design", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Review a pack_design.json blueprint", stdout.getvalue())

    def test_cli_help_includes_blueprint_pack(self):
        from mythweaver.cli.main import _fallback_main

        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            _fallback_main(["blueprint-pack", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Generate a deterministic mod selection blueprint", stdout.getvalue())

    def test_infers_common_archetypes_from_concepts(self):
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        cases = {
            "vanilla plus enhanced vanilla with little QoL": "vanilla_plus",
            "expert greg tech automation chain with hard recipes": "expert_tech",
            "skyblock island in the void with quests": "skyblock",
            "horror survival in darkness with parasites": "horror_survival",
            "cozy farming peaceful Stardew village cooking": "cozy_farming",
        }

        for concept, archetype in cases.items():
            with self.subTest(archetype=archetype):
                design = infer_pack_design_from_concept(concept)
                self.assertEqual(design.archetype, archetype)
                self.assertIn("performance_foundation", design.required_systems)

    def test_design_pack_writes_pack_design_json_and_prompt(self):
        from mythweaver.cli.main import _fallback_main
        from mythweaver.schemas.contracts import PackDesign

        root = Path.cwd() / "output" / "test-design-pack-cli"
        root.mkdir(parents=True, exist_ok=True)
        concept = root / "concept.md"
        concept.write_text("A vanilla+ enhanced vanilla pack with QoL and ambience.", encoding="utf-8")

        stdout = StringIO()
        with redirect_stdout(stdout):
            result = _fallback_main(["design-pack", str(concept), "--output-dir", str(root), "--name", "Soft Vanilla"])

        self.assertEqual(result, 0)
        written = root / "pack_design.json"
        self.assertTrue(written.is_file())
        self.assertTrue((root / "cloud_ai_design_prompt.md").is_file())
        design = PackDesign.model_validate_json(written.read_text(encoding="utf-8"))
        self.assertEqual(design.name, "Soft Vanilla")
        self.assertEqual(design.archetype, "vanilla_plus")

    def test_review_design_flags_vague_custom_design(self):
        from mythweaver.pipeline.pack_quality import review_pack_design
        from mythweaver.schemas.contracts import PackDesign

        design = PackDesign(name="Vague", summary="Lots of cool fun mods.", archetype="custom")

        report = review_pack_design(design)

        self.assertEqual(report.readiness, "not_enough_direction")
        self.assertTrue(any(issue.severity in {"high", "critical"} for issue in report.issues))
        self.assertIn("core loop", " ".join(report.missing_design_elements).lower())

    def test_review_design_passes_strong_design(self):
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept, review_pack_design

        design = infer_pack_design_from_concept("expert greg tech automation chain with hard recipes and final factory goal")
        report = review_pack_design(design)

        self.assertEqual(report.readiness, "ready_for_mod_selection")
        self.assertGreaterEqual(report.score, 80)

    def test_review_design_cli_writes_report_and_repair_prompt(self):
        from mythweaver.cli.main import _fallback_main
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept

        root = Path.cwd() / "output" / "test-review-design-cli"
        root.mkdir(parents=True, exist_ok=True)
        design_path = root / "pack_design.json"
        design = infer_pack_design_from_concept("cozy farming village cooking decoration")
        design_path.write_text(design.model_dump_json(indent=2), encoding="utf-8")

        stdout = StringIO()
        with redirect_stdout(stdout):
            result = _fallback_main(["review-design", str(design_path)])

        self.assertEqual(result, 0)
        report = json.loads((root / "design_review_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["design"]["archetype"], "cozy_farming")
        self.assertTrue((root / "cloud_ai_design_repair_prompt.md").is_file())

    def test_blueprint_pack_writes_blueprint_and_selection_prompt(self):
        from mythweaver.cli.main import _fallback_main
        from mythweaver.pipeline.pack_quality import infer_pack_design_from_concept
        from mythweaver.schemas.contracts import PackBlueprint

        root = Path.cwd() / "output" / "test-blueprint-pack-cli"
        root.mkdir(parents=True, exist_ok=True)
        design_path = root / "pack_design.json"
        design = infer_pack_design_from_concept("vanilla plus enhanced vanilla with quality of life")
        design_path.write_text(design.model_dump_json(indent=2), encoding="utf-8")

        stdout = StringIO()
        with redirect_stdout(stdout):
            result = _fallback_main(["blueprint-pack", str(design_path), "--output-dir", str(root)])

        self.assertEqual(result, 0)
        blueprint_path = root / "pack_blueprint.json"
        self.assertTrue(blueprint_path.is_file())
        self.assertTrue((root / "cloud_ai_selection_prompt.md").is_file())
        blueprint = PackBlueprint.model_validate_json(blueprint_path.read_text(encoding="utf-8"))
        self.assertEqual(blueprint.archetype, "vanilla_plus")
        self.assertTrue(blueprint.cloud_ai_prompt_path)

    def test_vanilla_plus_blueprint_has_small_range_and_heavy_system_avoidance(self):
        from mythweaver.pipeline.pack_quality import generate_pack_blueprint, infer_pack_design_from_concept

        blueprint = generate_pack_blueprint(infer_pack_design_from_concept("vanilla plus enhanced vanilla QoL"))
        avoid_text = " ".join(rule for slot in blueprint.forbidden_slots + blueprint.required_slots for rule in slot.avoid_rules).lower()

        self.assertEqual((blueprint.target_mod_count_min, blueprint.target_mod_count_max), (25, 70))
        self.assertIn("tech", {slot.system_tag for slot in blueprint.forbidden_slots})
        self.assertIn("heavy", avoid_text)

    def test_horror_blueprint_avoids_comfort_power_creep(self):
        from mythweaver.pipeline.pack_quality import generate_pack_blueprint, infer_pack_design_from_concept

        blueprint = generate_pack_blueprint(infer_pack_design_from_concept("horror survival darkness parasites scarce supplies"))
        forbidden = {slot.system_tag for slot in blueprint.forbidden_slots}
        map_slots = [slot for slot in blueprint.required_slots + blueprint.recommended_slots + blueprint.optional_slots if slot.system_tag == "map_tools"]

        self.assertTrue({"full_map_reveal", "too_much_fast_travel", "overpowered_gear"} <= forbidden)
        self.assertFalse(any(slot.priority == "required" for slot in map_slots))

    def test_expert_tech_blueprint_includes_chain_systems_and_config_expectations(self):
        from mythweaver.pipeline.pack_quality import generate_pack_blueprint, infer_pack_design_from_concept

        blueprint = generate_pack_blueprint(infer_pack_design_from_concept("expert greg tech automation hard recipes final factory"))
        required = {slot.system_tag for slot in blueprint.required_slots}

        self.assertTrue({"automation", "recipe_progression", "power_generation", "logistics", "storage_solution"} <= required)
        self.assertTrue(any("recipe" in item.lower() for item in blueprint.config_or_datapack_expectations))

    def test_cozy_blueprint_prioritizes_farm_home_and_avoids_danger(self):
        from mythweaver.pipeline.pack_quality import generate_pack_blueprint, infer_pack_design_from_concept

        blueprint = generate_pack_blueprint(infer_pack_design_from_concept("cozy farming peaceful village cooking decoration"))
        required = {slot.system_tag for slot in blueprint.required_slots}
        forbidden = {slot.system_tag for slot in blueprint.forbidden_slots}

        self.assertTrue({"farming", "cooking", "animals", "decoration"} <= required)
        self.assertTrue({"horror_mobs", "hardcore_survival"} <= forbidden)

    def test_skyblock_blueprint_requires_void_resource_path_and_warns_about_overworld_dependencies(self):
        from mythweaver.pipeline.pack_quality import generate_pack_blueprint, infer_pack_design_from_concept

        blueprint = generate_pack_blueprint(infer_pack_design_from_concept("skyblock island void quests automation resources"))
        required = {slot.system_tag for slot in blueprint.required_slots}
        caution_text = " ".join(blueprint.compatibility_cautions).lower()

        self.assertTrue({"skyblock_resource_path", "resource_generation"} <= required)
        self.assertIn("overworld", caution_text)

    def test_cloud_ai_blueprint_selection_prompt_has_selected_mods_guardrails(self):
        from mythweaver.handoff import write_cloud_ai_blueprint_selection_prompt
        from mythweaver.pipeline.pack_quality import generate_pack_blueprint, infer_pack_design_from_concept

        root = Path.cwd() / "output" / "test-blueprint-prompt"
        root.mkdir(parents=True, exist_ok=True)
        design_path = root / "pack_design.json"
        design = infer_pack_design_from_concept("cozy farming peaceful village cooking decoration")
        design_path.write_text(design.model_dump_json(indent=2), encoding="utf-8")
        prompt_path = write_cloud_ai_blueprint_selection_prompt(design_path, generate_pack_blueprint(design), output_dir=root)

        text = prompt_path.read_text(encoding="utf-8")
        self.assertIn("selected_mods.json only", text)
        self.assertIn("Respect min/max slot guidance", text)
        self.assertIn("Do not add RPG/tech/horror/etc. systems unless blueprint asks for them", text)


if __name__ == "__main__":
    unittest.main()
