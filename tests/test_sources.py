import json
import unittest
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.test_agent_selected_workflow import FakeAgentFacade, project_payload
from tests.test_pipeline_discovery import version_payload
from tests.test_runtime_stabilization import RuntimeFacade


class SourceLayerTests(unittest.IsolatedAsyncioTestCase):
    def selected(self, mods):
        from mythweaver.schemas.contracts import SelectedModList

        return SelectedModList.model_validate(
            {
                "name": "Source Pack",
                "summary": "Testing source acquisition.",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": mods,
            }
        )

    def make_fabric_jar(self, path: Path, *, loader="fabric", version="1.20.1"):
        path.parent.mkdir(parents=True, exist_ok=True)
        fabric = {
            "schemaVersion": 1,
            "id": "local_test_mod",
            "version": "1.0.0",
            "depends": {"minecraft": version, "fabricloader": ">=0.14.0"} if loader == "fabric" else {"minecraft": version},
        }
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("fabric.mod.json", json.dumps(fabric))
        return path

    def test_provider_protocol_with_fake_provider_and_unknown_source_rejected(self):
        from mythweaver.sources.base import SourceProvider
        from mythweaver.sources.resolver import provider_for_source

        class FakeProvider:
            source_name = "fake"
            trust_tier = "official_api"

            def is_configured(self):
                return True

            async def search(self, query, *, minecraft_version, loader, limit=20):
                return None

            async def inspect(self, project_ref, *, minecraft_version, loader):
                return None

            async def resolve_file(self, project_ref, *, minecraft_version, loader):
                return None

        self.assertTrue(isinstance(FakeProvider(), SourceProvider))
        with self.assertRaises(ValueError):
            provider_for_source("not-a-source", modrinth=None)

    async def test_modrinth_candidate_matching_loader_version_is_verified_auto(self):
        from mythweaver.sources.modrinth import ModrinthSourceProvider

        provider = ModrinthSourceProvider(RuntimeFacade().modrinth)
        result = await provider.search("sodium", minecraft_version="1.20.1", loader="fabric", limit=5)

        self.assertTrue(result.candidates)
        self.assertEqual(result.candidates[0].source, "modrinth")
        self.assertEqual(result.candidates[0].acquisition_status, "verified_auto")
        self.assertTrue(result.candidates[0].hashes)

    async def test_curseforge_no_api_key_warns_not_configured(self):
        from mythweaver.sources.curseforge import CurseForgeSourceProvider

        provider = CurseForgeSourceProvider(api_key=None)
        result = await provider.search("chipped", minecraft_version="1.20.1", loader="fabric")

        self.assertFalse(provider.is_configured())
        self.assertIn("CURSEFORGE_API_KEY", " ".join(result.warnings))
        self.assertFalse(result.candidates)

    async def test_curseforge_mocked_matching_file_is_verified_auto(self):
        from mythweaver.sources.curseforge import CurseForgeSourceProvider

        payloads = {
            "/v1/mods/search": {
                "data": [{"id": 10, "slug": "mock-mod", "name": "Mock Mod", "links": {"websiteUrl": "https://www.curseforge.com/minecraft/mc-mods/mock-mod"}}]
            },
            "/v1/mods/10/files": {
                "data": [
                    {
                        "id": 99,
                        "displayName": "Mock Mod Fabric 1.20.1",
                        "fileName": "mock-mod-fabric-1.20.1.jar",
                        "downloadUrl": "https://edge.forgecdn.net/files/mock.jar",
                        "gameVersions": ["1.20.1", "Fabric"],
                        "hashes": [{"algo": 1, "value": "abc123"}],
                        "fileLength": 1234,
                        "dependencies": [{"modId": 11, "relationType": 3}],
                    }
                ]
            },
        }
        provider = CurseForgeSourceProvider(api_key="test", request_json=lambda path, params=None: payloads[path])
        candidate = await provider.resolve_file("mock-mod", minecraft_version="1.20.1", loader="fabric")

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.source, "curseforge")
        self.assertEqual(candidate.acquisition_status, "verified_auto")
        self.assertIn("sha1", candidate.hashes)
        self.assertEqual(candidate.dependencies, ["11"])

    async def test_curseforge_missing_loader_is_unsupported_or_incomplete(self):
        from mythweaver.sources.curseforge import CurseForgeSourceProvider

        payloads = {
            "/v1/mods/10": {"data": {"id": 10, "slug": "forge-mod", "name": "Forge Mod"}},
            "/v1/mods/10/files": {
                "data": [
                    {
                        "id": 1,
                        "displayName": "Forge Mod",
                        "fileName": "forge-mod.jar",
                        "downloadUrl": "https://edge.forgecdn.net/files/forge.jar",
                        "gameVersions": ["1.20.1", "Forge"],
                        "hashes": [{"algo": 1, "value": "abc123"}],
                    }
                ]
            },
        }
        provider = CurseForgeSourceProvider(api_key="test", request_json=lambda path, params=None: payloads[path])
        candidate = await provider.resolve_file("10", minecraft_version="1.20.1", loader="fabric")

        self.assertIsNotNone(candidate)
        self.assertIn(candidate.acquisition_status, {"unsupported", "metadata_incomplete"})

    async def test_planet_minecraft_is_manual_discovery_only(self):
        from mythweaver.sources.planetminecraft import PlanetMinecraftSourceProvider

        provider = PlanetMinecraftSourceProvider()
        candidate = await provider.inspect("https://www.planetminecraft.com/mod/example/", minecraft_version="1.20.1", loader="fabric")

        self.assertEqual(candidate.source, "planetminecraft")
        self.assertNotEqual(candidate.acquisition_status, "verified_auto")
        self.assertIn("manual review", " ".join(candidate.warnings).lower())

    async def test_local_fabric_jar_hashes_and_metadata(self):
        from mythweaver.sources.local import LocalFileSourceProvider

        jar = self.make_fabric_jar(Path.cwd() / "output" / "test-local-source" / "local-test.jar")
        candidate = await LocalFileSourceProvider().inspect(f"local:{jar}", minecraft_version="1.20.1", loader="fabric")

        self.assertEqual(candidate.source, "local")
        self.assertEqual(candidate.acquisition_status, "verified_auto")
        self.assertIn("sha1", candidate.hashes)
        self.assertIn("sha512", candidate.hashes)

    async def test_local_wrong_loader_or_version_is_not_verified(self):
        from mythweaver.sources.local import LocalFileSourceProvider

        jar = self.make_fabric_jar(Path.cwd() / "output" / "test-local-source-wrong" / "local-test.jar", version="1.19.2")
        candidate = await LocalFileSourceProvider().inspect(f"local:{jar}", minecraft_version="1.20.1", loader="fabric")

        self.assertNotEqual(candidate.acquisition_status, "verified_auto")

    def test_policy_blocks_manual_and_unsafe_sources(self):
        from mythweaver.schemas.contracts import SourceFileCandidate
        from mythweaver.sources.policy import evaluate_candidate_policy

        manual = SourceFileCandidate(source="planetminecraft", name="PMC Mod", acquisition_status="verified_manual_required")
        unsafe = SourceFileCandidate(source="direct_url", name="Direct", acquisition_status="unsafe_source")

        self.assertEqual(
            evaluate_candidate_policy(manual, target_export="local_instance", autonomous=True).acquisition_status,
            "download_blocked",
        )
        self.assertEqual(
            evaluate_candidate_policy(unsafe, target_export="local_instance", autonomous=False).acquisition_status,
            "unsafe_source",
        )

    def test_policy_allows_verified_local_instance_but_blocks_modrinth_pack_external(self):
        from mythweaver.schemas.contracts import SourceFileCandidate
        from mythweaver.sources.policy import evaluate_candidate_policy

        local = SourceFileCandidate(
            source="local",
            name="Local Mod",
            loaders=["fabric"],
            minecraft_versions=["1.20.1"],
            hashes={"sha1": "abc"},
            acquisition_status="verified_auto",
        )
        self.assertEqual(
            evaluate_candidate_policy(local, target_export="local_instance", autonomous=True).acquisition_status,
            "verified_auto",
        )
        self.assertEqual(
            evaluate_candidate_policy(local, target_export="modrinth_pack", autonomous=True).acquisition_status,
            "download_blocked",
        )

    async def test_resolver_prefers_modrinth_and_places_manual_in_manual_required(self):
        from mythweaver.sources.resolver import resolve_sources_for_selected_mods

        selected = self.selected(
            [
                {"slug": "sodium", "role": "foundation", "reason_selected": "Performance"},
                {
                    "slug": "example",
                    "role": "theme",
                    "reason_selected": "PMC example",
                    "source": "planetminecraft",
                    "source_ref": "https://www.planetminecraft.com/mod/example/",
                },
            ]
        )
        report = await resolve_sources_for_selected_mods(
            selected,
            minecraft_version="1.20.1",
            loader="fabric",
            sources=["modrinth", "planetminecraft"],
            target_export="local_instance",
            autonomous=True,
            modrinth=RuntimeFacade().modrinth,
        )

        self.assertEqual(report.status, "partial")
        self.assertTrue(any(candidate.source == "modrinth" for candidate in report.selected_files))
        self.assertTrue(report.manual_required or report.blocked)

    def test_cli_source_commands_have_help(self):
        from mythweaver.cli.main import _fallback_main

        for command in ["source-search", "source-inspect", "source-resolve"]:
            stdout = StringIO()
            with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
                _fallback_main([command, "--help"])
            self.assertEqual(raised.exception.code, 0)
            self.assertTrue(stdout.getvalue())

    def test_agent_workflow_prompt_mentions_source_policy(self):
        from mythweaver.handoff import write_agent_workflow_prompt

        root = Path.cwd() / "output" / "test-source-workflow"
        concept = root / "concept.md"
        root.mkdir(parents=True, exist_ok=True)
        concept.write_text("# Source Workflow\n\nUse safe sources.", encoding="utf-8")
        report = write_agent_workflow_prompt(concept, concept.read_text(encoding="utf-8"), output_dir=root)
        text = Path(report.prompt_path).read_text(encoding="utf-8")

        self.assertIn("source-resolve", text)
        self.assertIn("verified_auto", text)
        self.assertIn("manual_required", text)
        self.assertIn("Do not scrape CurseForge or Planet Minecraft", text)
        self.assertIn("Do not silently use external direct downloads", text)

    def test_readme_documents_multi_source_acquisition(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("Multi-source mod acquisition", readme)
        self.assertIn("CURSEFORGE_API_KEY", readme)
        self.assertIn("Planet Minecraft", readme)
        self.assertIn("source-resolve selected_mods.json", readme)

    async def test_agent_check_reports_manual_source_warning(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        selected = self.selected(
            [
                {
                    "slug": "example",
                    "role": "theme",
                    "reason_selected": "Manual source",
                    "source": "planetminecraft",
                    "source_ref": "https://www.planetminecraft.com/mod/example/",
                }
            ]
        )
        report = await AgentModpackService(RuntimeFacade()).agent_check(selected, sources=["planetminecraft"], target_export="local_instance")

        self.assertTrue(any(finding.kind == "technical_blocker" for finding in report.hard_blockers + report.warnings))

    async def test_autonomous_build_blocks_manual_sources_by_default(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        root = Path.cwd() / "output" / "test-autonomous-manual-source"
        concept = root / "concept.md"
        root.mkdir(parents=True, exist_ok=True)
        concept.write_text("# Manual Source\n\nUse a manual mod.", encoding="utf-8")
        selected = self.selected(
            [
                {
                    "slug": "example",
                    "role": "theme",
                    "reason_selected": "Manual source",
                    "source": "planetminecraft",
                    "source_ref": "https://www.planetminecraft.com/mod/example/",
                }
            ]
        )
        report = await AgentModpackService(RuntimeFacade()).autonomous_build(
            concept,
            root,
            selected=selected,
            sources=["planetminecraft"],
            target_export="local_instance",
        )

        self.assertNotEqual(report.status, "stable")
        self.assertTrue(any("manual" in step.lower() for step in report.user_next_steps))

    async def test_dependency_closure_rejects_missing_transitive_dependency(self):
        from mythweaver.schemas.contracts import SourceDependencyRecord, SourceFileCandidate
        from mythweaver.sources.resolver import resolve_sources_for_selected_mods

        main = SourceFileCandidate(
            source="modrinth",
            project_id="main",
            slug="main",
            name="Main",
            acquisition_status="verified_auto",
            dependency_records=[SourceDependencyRecord(source="modrinth", project_id="missing-lib", dependency_type="required")],
        )
        providers = {"modrinth": FakeClosureProvider("modrinth", {"main": main})}

        with patch("mythweaver.sources.resolver.provider_for_source", lambda source, **kwargs: providers[source]):
            report = await resolve_sources_for_selected_mods(
                self.selected([{"slug": "main", "role": "theme", "reason_selected": "Main content"}]),
                minecraft_version="1.20.1",
                loader="fabric",
                sources=["modrinth"],
                target_export="local_instance",
                autonomous=True,
            )

        self.assertFalse(report.dependency_closure_passed)
        self.assertEqual(report.unresolved_required_dependencies[0].project_id, "missing-lib")

    async def test_dependency_closure_handles_curseforge_only_dependency_policy(self):
        from mythweaver.schemas.contracts import SourceDependencyRecord, SourceFileCandidate
        from mythweaver.sources.resolver import resolve_sources_for_selected_mods

        main = SourceFileCandidate(
            source="modrinth",
            project_id="main",
            slug="main",
            name="Main",
            acquisition_status="verified_auto",
            dependency_records=[SourceDependencyRecord(source="curseforge", project_id="12345", dependency_type="required")],
        )
        curse_dep = SourceFileCandidate(
            source="curseforge",
            project_id="12345",
            name="CurseForge Lib",
            acquisition_status="verified_auto",
        )
        providers = {
            "modrinth": FakeClosureProvider("modrinth", {"main": main}),
            "curseforge": FakeClosureProvider("curseforge", {"12345": curse_dep}),
        }

        with patch("mythweaver.sources.resolver.provider_for_source", lambda source, **kwargs: providers[source]):
            blocked = await resolve_sources_for_selected_mods(
                self.selected([{"slug": "main", "role": "theme", "reason_selected": "Main content"}]),
                minecraft_version="1.20.1",
                loader="fabric",
                sources=["modrinth"],
                target_export="local_instance",
                autonomous=True,
            )
            resolved = await resolve_sources_for_selected_mods(
                self.selected([{"slug": "main", "role": "theme", "reason_selected": "Main content"}]),
                minecraft_version="1.20.1",
                loader="fabric",
                sources=["modrinth", "curseforge"],
                target_export="local_instance",
                autonomous=True,
            )

        self.assertFalse(blocked.dependency_closure_passed)
        self.assertTrue(blocked.manually_required_dependencies)
        self.assertTrue(resolved.dependency_closure_passed)
        self.assertEqual(resolved.dependency_source_breakdown["curseforge"], 1)

    async def test_optional_dependency_warns_without_blocking_closure(self):
        from mythweaver.schemas.contracts import SourceDependencyRecord, SourceFileCandidate
        from mythweaver.sources.resolver import resolve_sources_for_selected_mods

        main = SourceFileCandidate(
            source="modrinth",
            project_id="main",
            slug="main",
            name="Main",
            acquisition_status="verified_auto",
            dependency_records=[SourceDependencyRecord(source="modrinth", project_id="nice-extra", dependency_type="optional")],
        )
        providers = {"modrinth": FakeClosureProvider("modrinth", {"main": main})}

        with patch("mythweaver.sources.resolver.provider_for_source", lambda source, **kwargs: providers[source]):
            report = await resolve_sources_for_selected_mods(
                self.selected([{"slug": "main", "role": "theme", "reason_selected": "Main content"}]),
                minecraft_version="1.20.1",
                loader="fabric",
                sources=["modrinth"],
                target_export="local_instance",
                autonomous=True,
            )

        self.assertTrue(report.dependency_closure_passed)
        self.assertEqual(report.optional_dependencies[0].project_id, "nice-extra")

    async def test_dependency_version_mismatch_rejects_closure(self):
        from mythweaver.schemas.contracts import SourceDependencyRecord, SourceFileCandidate
        from mythweaver.sources.resolver import resolve_sources_for_selected_mods

        main = SourceFileCandidate(
            source="modrinth",
            project_id="main",
            slug="main",
            name="Main",
            acquisition_status="verified_auto",
            dependency_records=[
                SourceDependencyRecord(source="modrinth", project_id="library", version_id="required-version", dependency_type="required")
            ],
        )
        wrong_library = SourceFileCandidate(
            source="modrinth",
            project_id="library",
            slug="library",
            name="Library",
            file_id="wrong-version",
            acquisition_status="verified_auto",
        )
        providers = {"modrinth": FakeClosureProvider("modrinth", {"main": main, "library": wrong_library})}

        with patch("mythweaver.sources.resolver.provider_for_source", lambda source, **kwargs: providers[source]):
            report = await resolve_sources_for_selected_mods(
                self.selected([{"slug": "main", "role": "theme", "reason_selected": "Main content"}]),
                minecraft_version="1.20.1",
                loader="fabric",
                sources=["modrinth"],
                target_export="local_instance",
                autonomous=True,
            )

        self.assertFalse(report.dependency_closure_passed)
        self.assertEqual(report.unresolved_required_dependencies[0].reason, "dependency_version_mismatch")

    async def test_croptopia_delight_style_dependency_chain_passes_when_croptopia_is_acquired(self):
        from mythweaver.schemas.contracts import SourceDependencyRecord, SourceFileCandidate
        from mythweaver.sources.resolver import resolve_sources_for_selected_mods

        delight = SourceFileCandidate(
            source="modrinth",
            project_id="croptopia-delight",
            slug="croptopia-delight",
            name="Croptopia Delight",
            acquisition_status="verified_auto",
            dependency_records=[
                SourceDependencyRecord(
                    source="modrinth",
                    project_id="croptopia",
                    required_version=">=3.0.3",
                    dependency_type="required",
                )
            ],
        )
        croptopia = SourceFileCandidate(
            source="modrinth",
            project_id="croptopia",
            slug="croptopia",
            name="Croptopia",
            version_number="3.0.4",
            acquisition_status="verified_auto",
        )
        providers = {"modrinth": FakeClosureProvider("modrinth", {"croptopia-delight": delight, "croptopia": croptopia})}

        with patch("mythweaver.sources.resolver.provider_for_source", lambda source, **kwargs: providers[source]):
            report = await resolve_sources_for_selected_mods(
                self.selected([{"slug": "croptopia-delight", "role": "theme", "reason_selected": "Cooking compatibility"}]),
                minecraft_version="1.20.1",
                loader="fabric",
                sources=["modrinth"],
                target_export="local_instance",
                autonomous=True,
            )

        self.assertTrue(report.dependency_closure_passed)
        self.assertEqual(report.transitive_dependency_count, 1)
        self.assertEqual({candidate.project_id for candidate in report.selected_files}, {"croptopia-delight", "croptopia"})


class FakeClosureProvider:
    def __init__(self, source_name, candidates):
        self.source_name = source_name
        self.candidates = candidates

    def is_configured(self):
        return True

    async def resolve_file(self, project_ref, *, minecraft_version, loader):
        return self.candidates.get(project_ref)
