import unittest


class ContractTests(unittest.TestCase):
    def test_requirement_profile_accepts_agent_supplied_structured_intent(self):
        from mythweaver.schemas.contracts import RequirementProfile

        profile = RequirementProfile(
            name="Infinite Winter",
            themes=["cosmic horror", "winter", "survival"],
            terrain=["snow", "mountains", "frozen oceans"],
            gameplay=["resource scarcity", "hostile nights"],
            mood=["isolated", "hopeless"],
            desired_systems=["temperature", "dynamic weather"],
            performance_target="balanced",
            multiplayer="singleplayer",
        )

        self.assertEqual(profile.loader, "fabric")
        self.assertEqual(profile.themes[0], "cosmic horror")
        self.assertEqual(profile.minecraft_version, "auto")

    def test_settings_do_not_require_an_ai_provider(self):
        from mythweaver.core.settings import Settings

        settings = Settings()

        self.assertFalse(settings.ai_enabled)
        self.assertIsNone(settings.ai_base_url)
        self.assertIn("MythWeaver", settings.modrinth_user_agent)

    def test_mod_file_rejects_bad_hashes_and_non_https_urls(self):
        from pydantic import ValidationError

        from mythweaver.schemas.contracts import ModFile

        with self.assertRaises(ValidationError):
            ModFile(
                filename="bad.jar",
                url="http://cdn.modrinth.com/data/a/versions/b/bad.jar",
                hashes={"sha1": "a" * 40, "sha512": "b" * 128},
                size=1,
            )

        with self.assertRaises(ValidationError):
            ModFile(
                filename="bad.jar",
                url="https://cdn.modrinth.com/data/a/versions/b/bad.jar",
                hashes={"sha1": "not-a-sha1", "sha512": "b" * 128},
                size=1,
            )

    def test_generation_report_has_foundation_confidence_and_next_action_fields(self):
        from mythweaver.schemas.contracts import GenerationReport, RequirementProfile

        report = GenerationReport(
            run_id="test-run",
            status="completed",
            profile=RequirementProfile(name="Report Pack"),
        )

        self.assertTrue(hasattr(report, "performance_foundation"))
        self.assertTrue(hasattr(report, "shader_support"))
        self.assertTrue(hasattr(report, "shader_recommendations"))
        self.assertTrue(hasattr(report, "confidence"))
        self.assertEqual(report.confidence.theme_match, 0.0)
        self.assertEqual(report.next_actions, [])


if __name__ == "__main__":
    unittest.main()
