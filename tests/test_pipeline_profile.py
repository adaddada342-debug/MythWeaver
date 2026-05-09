import unittest


class PipelineProfileTests(unittest.TestCase):
    def test_extracts_winter_horror_profile_from_prompt(self):
        from mythweaver.pipeline.profile import profile_from_prompt

        profile = profile_from_prompt(
            "I want a horrifying infinite winter survival world with ancient ruins."
        )

        self.assertEqual(profile.loader, "fabric")
        self.assertEqual(profile.minecraft_version, "auto")
        self.assertIn("winter", profile.themes)
        self.assertIn("horror", profile.themes)
        self.assertIn("survival", profile.gameplay)
        self.assertIn("structures", profile.desired_systems)

    def test_extracts_cozy_fantasy_profile_from_prompt(self):
        from mythweaver.pipeline.profile import profile_from_prompt

        profile = profile_from_prompt("A peaceful fantasy farming RPG with dragons and cozy villages")

        self.assertIn("fantasy", profile.themes)
        self.assertIn("cozy", profile.mood)
        self.assertIn("farming", profile.gameplay)
        self.assertIn("dragons", profile.desired_systems)

    def test_extracts_australian_outback_zombie_apocalypse_profile(self):
        from mythweaver.pipeline.profile import profile_from_prompt

        profile = profile_from_prompt(
            "Australian outback post apocalyptic zombie survival with ruined towns harsh heat scarce resources cinematic atmosphere"
        )

        self.assertIn("post-apocalyptic", profile.themes)
        self.assertIn("zombie survival", profile.themes)
        self.assertTrue({"outback", "wasteland"} & set(profile.themes))
        self.assertTrue({"desert", "dry plains", "badlands", "wasteland"} & set(profile.terrain))
        self.assertIn("survival", profile.gameplay)
        self.assertTrue({"scavenging", "resource scarcity"} <= set(profile.gameplay))
        self.assertIn("heat management", profile.gameplay)
        self.assertIn("cinematic", profile.mood)
        self.assertIn("harsh", profile.mood)
        self.assertTrue({"dusty", "isolated"} & set(profile.mood))
        self.assertIn("zombies", profile.desired_systems)
        self.assertTrue({"ruins", "structures", "abandoned settlements"} & set(profile.desired_systems))
        self.assertTrue({"thirst", "temperature", "survival mechanics"} & set(profile.desired_systems))
        self.assertIn("atmosphere", profile.desired_systems)


if __name__ == "__main__":
    unittest.main()
