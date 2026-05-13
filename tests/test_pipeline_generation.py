import json
import unittest
import zipfile
from pathlib import Path

from tests.test_pipeline_discovery import version_payload


class FakeFacade:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.modrinth = FakePipelineModrinth()

    def score_candidates(self, candidates, profile):
        from mythweaver.catalog.scoring import score_candidates

        return score_candidates(candidates, profile)

    def resolve_dependencies(self, requested_project_ids, candidates, profile, loader_version=None):
        from mythweaver.resolver.engine import resolve_pack

        return resolve_pack(requested_project_ids, candidates, profile, loader_version)

    def detect_conflicts(self, candidates):
        return []

    async def build_pack(self, pack, output_dir, download=True):
        from mythweaver.builders.mrpack import build_mrpack

        return [build_mrpack(pack, output_dir / "pack.mrpack")]

    def generate_configs(self, profile, output_dir):
        from mythweaver.configs.datapack import generate_lore_datapack

        return generate_lore_datapack(profile, output_dir / "datapack")

    def validate_launch(self, instance_id):
        from mythweaver.schemas.contracts import ValidationReport

        return ValidationReport(status="skipped", details="Prism not configured in test.")


class FakePipelineModrinth:
    async def search_projects(self, plan):
        if plan.query in {"winter", "survival", "temperature", "structures", "sodium", "iris shaders"}:
            project_id = plan.query.replace(" ", "-")
            return {
                "hits": [
                    {
                        "project_id": project_id,
                        "slug": project_id,
                        "title": plan.query.title(),
                        "description": f"{plan.query} winter survival temperature",
                        "categories": ["optimization"] if plan.query in {"sodium", "iris shaders"} else ["adventure"],
                        "client_side": "required",
                        "server_side": "optional",
                        "downloads": 1000,
                        "follows": 100,
                        "versions": ["1.20.1"],
                    }
                ]
            }
        return {"hits": []}

    async def list_project_versions(self, project_id_or_slug, *, loader, minecraft_version, include_changelog=False, use_loader_filter=True, **kwargs):
        return [version_payload(project_id_or_slug, game_versions=["1.20.1"])]


class PipelineGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_modpack_dry_run_writes_reports_and_mrpack(self):
        from mythweaver.pipeline.service import GenerationPipeline
        from mythweaver.schemas.contracts import GenerationRequest

        output_dir = Path.cwd() / "output" / "test-generation"
        pipeline = GenerationPipeline(FakeFacade(output_dir))

        report = await pipeline.generate(
            GenerationRequest(prompt="horrifying winter survival", output_dir=str(output_dir), dry_run=True)
        )

        self.assertEqual(report.status, "completed")
        self.assertEqual(report.validation.status, "skipped")
        self.assertTrue(report.selected_mods)
        self.assertTrue(report.performance_foundation.performance_enabled)
        self.assertTrue(report.performance_foundation.selected_mods)
        self.assertTrue(report.shader_support.enabled)
        self.assertTrue(report.shader_recommendations.primary.name)
        self.assertGreater(report.confidence.performance_foundation, 0)
        self.assertIn("install_shader_manually", report.next_actions)
        self.assertTrue((output_dir / "generation_report.json").is_file())
        self.assertTrue((output_dir / "generation_report.md").is_file())
        self.assertTrue(any(artifact.kind == "mrpack" for artifact in report.artifacts))

    async def test_generate_modpack_reports_discovery_empty(self):
        from mythweaver.pipeline.service import GenerationPipeline
        from mythweaver.schemas.contracts import GenerationRequest

        class EmptyFacade(FakeFacade):
            def __init__(self, output_dir):
                super().__init__(output_dir)
                self.modrinth = EmptyModrinth()

        class EmptyModrinth:
            async def search_projects(self, plan):
                return {"hits": []}

            async def list_project_versions(self, *args, **kwargs):
                return []

        output_dir = Path.cwd() / "output" / "test-generation-empty"
        pipeline = GenerationPipeline(EmptyFacade(output_dir))

        report = await pipeline.generate(
            GenerationRequest(prompt="impossible pack", output_dir=str(output_dir), dry_run=True)
        )

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.failed_stage, "discovery_empty")

    async def test_generation_request_requires_prompt_or_profile(self):
        from pydantic import ValidationError

        from mythweaver.schemas.contracts import GenerationRequest

        with self.assertRaises(ValidationError):
            GenerationRequest()

    async def test_generate_modpack_reports_discovery_error(self):
        from mythweaver.pipeline.service import GenerationPipeline
        from mythweaver.schemas.contracts import GenerationRequest

        class ErrorFacade(FakeFacade):
            def __init__(self, output_dir):
                super().__init__(output_dir)
                self.modrinth = ErrorModrinth()

        class ErrorModrinth:
            async def search_projects(self, plan):
                raise OSError("network unavailable")

        output_dir = Path.cwd() / "output" / "test-generation-error"
        pipeline = GenerationPipeline(ErrorFacade(output_dir))

        report = await pipeline.generate(
            GenerationRequest(prompt="winter survival", output_dir=str(output_dir), dry_run=True)
        )

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.failed_stage, "discovery_error")
        self.assertIn("network unavailable", report.stages[-1].message)

    async def test_dependency_expansion_is_consumed_by_resolver_and_export(self):
        from mythweaver.pipeline.service import GenerationPipeline
        from mythweaver.schemas.contracts import GenerationRequest, RequirementProfile

        class DependencyExpansionModrinth:
            async def search_projects(self, plan):
                if plan.query != "winter":
                    return {"hits": []}
                return {
                    "hits": [
                        {
                            "project_id": "winter-a",
                            "slug": "winter-a",
                            "title": "Winter A",
                            "description": "Winter cold survival structures.",
                            "categories": ["adventure"],
                            "client_side": "required",
                            "server_side": "optional",
                            "downloads": 1000,
                            "follows": 100,
                            "versions": ["1.20.1"],
                        }
                    ]
                }

            async def get_project(self, project_id_or_slug):
                if project_id_or_slug == "library-b":
                    return {
                        "id": "library-b",
                        "project_id": "library-b",
                        "slug": "library-b",
                        "title": "Library B",
                        "description": "Required library for Winter A.",
                        "categories": ["library"],
                        "client_side": "required",
                        "server_side": "required",
                        "downloads": 100,
                        "follows": 10,
                        "versions": ["1.20.1"],
                    }
                return {}

            async def list_project_versions(self, project_id_or_slug, *, loader, minecraft_version, include_changelog=False, use_loader_filter=True, **kwargs):
                version = version_payload(project_id_or_slug, game_versions=["1.20.1"])
                if project_id_or_slug == "winter-a":
                    version["dependencies"] = [
                        {"project_id": "library-b", "dependency_type": "required"}
                    ]
                return [version]

        class TrackingFacade(FakeFacade):
            def __init__(self, output_dir):
                super().__init__(output_dir)
                self.modrinth = DependencyExpansionModrinth()
                self.resolve_inputs = None
                self.built_pack_ids = []

            def resolve_dependencies(self, requested_project_ids, candidates, profile, loader_version=None):
                self.resolve_inputs = (
                    list(requested_project_ids),
                    [candidate.project_id for candidate in candidates],
                )
                return super().resolve_dependencies(requested_project_ids, candidates, profile, loader_version)

            async def build_pack(self, pack, output_dir, download=True):
                self.built_pack_ids = [candidate.project_id for candidate in pack.selected_mods]
                return await super().build_pack(pack, output_dir, download)

        output_dir = Path.cwd() / "output" / "test-dependency-expansion-consumed"
        facade = TrackingFacade(output_dir)
        profile = RequirementProfile(
            name="Dependency Expansion",
            search_keywords=["winter"],
            max_selected_before_dependencies=5,
        )

        report = await GenerationPipeline(facade).generate(
            GenerationRequest(profile=profile, output_dir=str(output_dir), dry_run=True, limit=5)
        )

        self.assertEqual(report.status, "completed")
        self.assertEqual({mod.project_id for mod in report.selected_theme_mods}, {"winter-a"})
        self.assertEqual({mod.project_id for mod in report.dependency_added_mods}, {"library-b"})
        self.assertEqual(set(facade.resolve_inputs[0]), {"winter-a", "library-b"})
        self.assertEqual(set(facade.resolve_inputs[1]), {"winter-a", "library-b"})
        self.assertEqual(set(facade.built_pack_ids), {"winter-a", "library-b"})
        self.assertEqual({mod.project_id for mod in report.selected_mods}, {"winter-a", "library-b"})
        self.assertTrue(
            any(edge.source_project_id == "winter-a" and edge.target_project_id == "library-b" for edge in report.dependency_edges)
        )

        mrpack = output_dir / "pack.mrpack"
        with zipfile.ZipFile(mrpack) as archive:
            index = json.loads(archive.read("modrinth.index.json"))
        paths = {file["path"] for file in index["files"]}
        self.assertEqual(paths, {"mods/winter-a.jar", "mods/library-b.jar"})


if __name__ == "__main__":
    unittest.main()
