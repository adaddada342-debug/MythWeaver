import unittest


def candidate(
    project_id: str,
    title: str,
    description: str,
    categories=None,
    downloads=10_000,
    follows=500,
    dependency_count=0,
    loaders=None,
    game_versions=None,
):
    from mythweaver.schemas.contracts import CandidateMod, ModFile, ModVersion

    version = ModVersion(
        id=f"{project_id}_version",
        project_id=project_id,
        version_number="1.0.0",
        game_versions=game_versions or ["1.20.1"],
        loaders=loaders or ["fabric"],
        version_type="release",
        status="listed",
        dependencies=[],
        files=[
            ModFile(
                filename=f"{project_id}.jar",
                url=f"https://cdn.modrinth.com/data/{project_id}/versions/1.0/{project_id}.jar",
                hashes={"sha1": "a" * 40, "sha512": "b" * 128},
                size=1234,
                primary=True,
            )
        ],
    )
    return CandidateMod(
        project_id=project_id,
        slug=project_id.lower(),
        title=title,
        description=description,
        categories=categories or [],
        client_side="required",
        server_side="optional",
        downloads=downloads,
        follows=follows,
        updated="2026-01-01T00:00:00Z",
        loaders=loaders or ["fabric"],
        game_versions=game_versions or ["1.20.1"],
        selected_version=version,
        dependency_count=dependency_count,
    )


class CandidateScoringTests(unittest.TestCase):
    def test_scores_thematically_relevant_mod_higher(self):
        from mythweaver.catalog.scoring import score_candidates
        from mythweaver.schemas.contracts import RequirementProfile

        profile = RequirementProfile(
            name="Winter Horror",
            themes=["winter", "horror"],
            terrain=["snow"],
            gameplay=["survival"],
            desired_systems=["temperature"],
        )
        winter = candidate(
            "winter1",
            "Frozen Nightmares",
            "Adds winter survival, temperature, snow storms, and horror nights.",
            categories=["adventure"],
            downloads=50_000,
        )
        tech = candidate(
            "tech1",
            "Factory Belts",
            "Adds automation factories and item transport.",
            categories=["technology"],
            downloads=500_000,
        )

        scored = score_candidates([tech, winter], profile)

        self.assertEqual(scored[0].project_id, "winter1")
        self.assertGreater(scored[0].score.total, scored[1].score.total)
        self.assertIn("theme:winter", scored[0].score.reasons)

    def test_rejects_wrong_loader(self):
        from mythweaver.catalog.scoring import score_candidates
        from mythweaver.schemas.contracts import RequirementProfile

        profile = RequirementProfile(name="Fabric Pack", themes=["magic"], minecraft_version="1.20.1")
        forge_only = candidate("forge1", "Forge Only", "Magic", loaders=["forge"])

        scored = score_candidates([forge_only], profile)

        self.assertEqual(scored[0].score.hard_reject_reason, "loader_mismatch")


if __name__ == "__main__":
    unittest.main()
