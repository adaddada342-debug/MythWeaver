import asyncio
import json
import unittest
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.test_pipeline_discovery import version_payload


def project_payload(project_id, *, slug=None, title=None, loaders=None, versions=None, categories=None, status="approved"):
    return {
        "id": project_id,
        "project_id": project_id,
        "slug": slug or project_id,
        "title": title or (slug or project_id).replace("-", " ").title(),
        "description": f"{title or slug or project_id} description",
        "categories": categories or ["adventure"],
        "client_side": "required",
        "server_side": "required",
        "downloads": 1000,
        "followers": 100,
        "follows": 100,
        "versions": versions or ["1.20.1"],
        "loaders": loaders or ["fabric"],
        "project_type": "mod",
        "status": status,
        "source_url": f"https://github.com/example/{slug or project_id}",
        "wiki_url": None,
        "issues_url": f"https://github.com/example/{slug or project_id}/issues",
    }


class FakeAgentModrinth:
    def __init__(self):
        self.projects = {
            "sodium": project_payload("sodium-id", slug="sodium", title="Sodium", categories=["optimization"]),
            "sodium-id": project_payload("sodium-id", slug="sodium", title="Sodium", categories=["optimization"]),
            "lithium": project_payload("lithium-id", slug="lithium", title="Lithium", categories=["optimization"]),
            "lithium-id": project_payload("lithium-id", slug="lithium", title="Lithium", categories=["optimization"]),
            "ferrite-core": project_payload("ferrite-id", slug="ferrite-core", title="FerriteCore", categories=["optimization"]),
            "iris": project_payload("iris-id", slug="iris", title="Iris Shaders", categories=["optimization"]),
            "when-dungeons-arise": project_payload(
                "dungeons-id",
                slug="when-dungeons-arise",
                title="When Dungeons Arise",
                categories=["adventure", "worldgen"],
            ),
            "library-b": project_payload("library-b", slug="library-b", title="Library B", categories=["library"]),
            "forge-only": project_payload("forge-only", slug="forge-only", title="Forge Only", loaders=["forge"]),
            "starlight-like": project_payload(
                "starlight-like",
                slug="starlight-like",
                title="Starlight Like",
                loaders=["fabric"],
                versions=["1.19.2"],
                categories=["optimization"],
            ),
        }
        self.versions = {
            "sodium": [version_payload("sodium-id")],
            "sodium-id": [version_payload("sodium-id")],
            "lithium": [version_payload("lithium-id")],
            "lithium-id": [version_payload("lithium-id")],
            "ferrite-core": [version_payload("ferrite-id")],
            "iris": [version_payload("iris-id")],
            "when-dungeons-arise": [
                version_payload(
                    "dungeons-id",
                    dependencies=[{"project_id": "library-b", "dependency_type": "required"}],
                )
            ],
            "dungeons-id": [
                version_payload(
                    "dungeons-id",
                    dependencies=[{"project_id": "library-b", "dependency_type": "required"}],
                )
            ],
            "library-b": [version_payload("library-b")],
            "forge-only": [version_payload("forge-only", loaders=["forge"])],
            "starlight-like": [version_payload("starlight-like", game_versions=["1.19.2"])],
        }

    async def search_projects(self, plan):
        hits = [
            project
            for project in self.projects.values()
            if plan.query.lower() in project["title"].lower() or plan.query.lower() in project["slug"].lower()
        ]
        return {"hits": hits[: plan.limit]}

    async def get_project(self, project_id_or_slug):
        if project_id_or_slug not in self.projects:
            raise KeyError(project_id_or_slug)
        return dict(self.projects[project_id_or_slug])

    async def list_project_versions(self, project_id_or_slug, *, loader, minecraft_version, include_changelog=False):
        return list(self.versions.get(project_id_or_slug, []))


class FakeAgentFacade:
    def __init__(self):
        self.modrinth = FakeAgentModrinth()
        self.built_pack_ids = []

    def resolve_dependencies(self, requested_project_ids, candidates, profile, loader_version=None):
        from mythweaver.resolver.engine import resolve_pack

        return resolve_pack(requested_project_ids, candidates, profile, loader_version)

    def detect_conflicts(self, candidates):
        return []

    async def build_pack(self, pack, output_dir, download=True):
        from mythweaver.builders.mrpack import build_mrpack

        output_dir.mkdir(parents=True, exist_ok=True)
        self.built_pack_ids = [candidate.project_id for candidate in pack.selected_mods]
        return [build_mrpack(pack, output_dir / "pack.mrpack")]


class AgentSelectedWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def selected_list(self):
        from mythweaver.schemas.contracts import SelectedModList

        return SelectedModList.model_validate(
            {
                "name": "Ashfall Frontier",
                "summary": "Volcanic frontier survival.",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "Renderer optimization"},
                    {"modrinth_id": "lithium-id", "role": "foundation", "reason_selected": "Logic optimization"},
                    {"slug": "iris", "role": "shader_support", "reason_selected": "Shader support"},
                    {"slug": "when-dungeons-arise", "role": "theme", "reason_selected": "Dungeons"},
                ],
            }
        )

    def test_selected_mod_list_schema_validation(self):
        selected = self.selected_list()
        from mythweaver.schemas.contracts import SelectedModEntry

        self.assertEqual(selected.name, "Ashfall Frontier")
        self.assertEqual(selected.mods[0].role, "foundation")
        with self.assertRaises(ValueError):
            SelectedModEntry.model_validate({"role": "theme"})

    async def test_verify_list_accepts_slug_or_modrinth_id(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        report = await AgentModpackService(FakeAgentFacade()).verify_mod_list(self.selected_list())

        self.assertEqual(report.status, "completed")
        self.assertIn("sodium-id", {mod.project_id for mod in report.user_selected_mods})
        self.assertIn("lithium-id", {mod.project_id for mod in report.user_selected_mods})

    async def test_verify_list_rejects_incompatible_loader_version(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import SelectedModList

        selected = SelectedModList.model_validate(
            {
                "name": "Bad Loader",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": [{"slug": "forge-only", "role": "theme"}],
            }
        )
        report = await AgentModpackService(FakeAgentFacade()).verify_mod_list(selected)

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.rejected_mods[0].reason, "no_compatible_installable_version")

    async def test_resolve_adds_missing_dependencies(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        report = await AgentModpackService(FakeAgentFacade()).resolve_mod_list(self.selected_list())

        self.assertEqual(report.status, "completed")
        self.assertIn("library-b", {mod.project_id for mod in report.dependency_added_mods})
        self.assertNotIn("library-b", {mod.project_id for mod in report.user_selected_mods})

    async def test_build_from_list_includes_user_selected_and_dependencies_in_mrpack(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        output_dir = Path.cwd() / "output" / "test-agent-selected-build"
        facade = FakeAgentFacade()
        report = await AgentModpackService(facade).build_from_list(self.selected_list(), output_dir, download=False)

        self.assertEqual(report.status, "completed")
        self.assertIn("library-b", {mod.project_id for mod in report.dependency_added_mods})
        self.assertIn("library-b", facade.built_pack_ids)
        with zipfile.ZipFile(output_dir / "pack.mrpack") as archive:
            index = json.loads(archive.read("modrinth.index.json"))
        self.assertIn("mods/library-b.jar", {file["path"] for file in index["files"]})

    async def test_do_not_build_review_blocks_build_unless_forced(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        output_dir = Path.cwd() / "output" / "test-agent-selected-review-gate"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "review_report.json").write_text(
            json.dumps(
                {
                    "run_id": "review-gate",
                    "status": "failed",
                    "name": "Ashfall Frontier",
                    "minecraft_version": "1.20.1",
                    "loader": "fabric",
                    "score": 10,
                    "verdict": "Do not build yet.",
                    "build_recommendation": "do_not_build",
                }
            ),
            encoding="utf-8",
        )
        facade = FakeAgentFacade()
        blocked = await AgentModpackService(facade).build_from_list(self.selected_list(), output_dir, download=False)

        self.assertEqual(blocked.status, "failed")
        self.assertEqual(blocked.failed_stage, "review_gate")
        self.assertFalse(facade.built_pack_ids)

        forced = await AgentModpackService(facade).build_from_list(self.selected_list(), output_dir, download=False, force=True)

        self.assertEqual(forced.status, "completed")
        self.assertIn("Forced build/export", " ".join(forced.compatibility_warnings))
        self.assertTrue(facade.built_pack_ids)

    async def test_removed_mod_audit_records_rejected_selected_mods(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import SelectedModList

        output_dir = Path.cwd() / "output" / "test-agent-selected-removed-audit"
        selected = SelectedModList.model_validate(
            {
                "name": "Audit Pack",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": [
                    {"slug": "sodium", "role": "foundation", "reason_selected": "performance_foundation"},
                    {"slug": "missing-cozy-mod", "role": "theme", "reason_selected": "farming cooking"},
                ],
            }
        )

        report = await AgentModpackService(FakeAgentFacade()).review_mod_list(selected, output_dir)

        self.assertEqual(report.build_recommendation, "do_not_build")
        self.assertEqual(report.removed_mods[0].slug_or_id, "missing-cozy-mod")
        self.assertEqual(report.removed_mods[0].reason, "invalid slug/project id")
        self.assertTrue((output_dir / "selected_mods.review_input.json").is_file())
        self.assertTrue((output_dir / "removed_mods.json").is_file())

    async def test_search_returns_installability_info(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        result = await AgentModpackService(FakeAgentFacade()).search_mods("sodium", loader="fabric", minecraft_version="1.20.1")

        self.assertTrue(result["results"][0]["installable"])
        self.assertIn("renderer_optimization", result["results"][0]["capabilities"])

    async def test_inspect_returns_compatible_version_dependency_info(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        result = await AgentModpackService(FakeAgentFacade()).inspect_mod(
            "when-dungeons-arise", loader="fabric", minecraft_version="1.20.1"
        )

        self.assertTrue(result["installable"])
        self.assertEqual(result["compatible_versions"][0]["dependencies"][0]["project_id"], "library-b")

    async def test_compare_returns_compatibility_differences(self):
        from mythweaver.pipeline.agent_service import AgentModpackService

        result = await AgentModpackService(FakeAgentFacade()).compare_mods(
            ["sodium", "forge-only"], loader="fabric", minecraft_version="1.20.1"
        )

        by_slug = {item["slug"]: item for item in result["candidates"]}
        self.assertTrue(by_slug["sodium"]["installable"])
        self.assertFalse(by_slug["forge-only"]["installable"])

    async def test_inspect_verify_search_and_compare_agree_when_project_exists_but_target_not_installable(self):
        from mythweaver.pipeline.agent_service import AgentModpackService
        from mythweaver.schemas.contracts import SelectedModList

        service = AgentModpackService(FakeAgentFacade())
        selected = SelectedModList.model_validate(
            {
                "name": "Starlight Check",
                "minecraft_version": "1.20.1",
                "loader": "fabric",
                "mods": [{"slug": "starlight-like", "role": "foundation"}],
            }
        )

        inspected = await service.inspect_mod("starlight-like", loader="fabric", minecraft_version="1.20.1")
        verified = await service.verify_mod_list(selected)
        searched = await service.search_mods("starlight", loader="fabric", minecraft_version="1.20.1")
        compared = await service.compare_mods(["starlight-like"], loader="fabric", minecraft_version="1.20.1")

        self.assertFalse(inspected["installable_for_requested_target"])
        self.assertEqual(inspected["installability_reason"], "minecraft_version_mismatch")
        self.assertEqual(inspected["compatible_versions_found"], 0)
        self.assertIsNone(inspected["selected_compatible_version"])
        self.assertTrue(inspected["loader_compatibility"])
        self.assertFalse(inspected["minecraft_version_compatibility"])
        self.assertTrue(inspected["installable_file_availability"])
        self.assertEqual(inspected["project_status"], "approved")
        self.assertEqual(inspected["version_status"], "listed")
        self.assertIn("Project exists, but no installable Fabric 1.20.1 version was found.", inspected["installability_message"])

        self.assertEqual(verified.rejected_mods[0].reason, "no_compatible_installable_version")
        self.assertIn("minecraft_version_mismatch", verified.rejected_mods[0].detail)
        self.assertFalse(searched["results"][0]["installable_for_requested_target"])
        self.assertEqual(searched["results"][0]["installability_reason"], "minecraft_version_mismatch")
        self.assertFalse(compared["candidates"][0]["installable_for_requested_target"])
        self.assertEqual(compared["candidates"][0]["installability_reason"], "minecraft_version_mismatch")


class AgentSelectedSurfaceTests(unittest.TestCase):
    def test_cli_commands_exist_and_show_help(self):
        from mythweaver.cli.main import main

        for command in ["search", "inspect", "compare", "verify-list", "resolve", "build-from-list", "agent-pack"]:
            stdout = StringIO()
            with self.assertRaises(SystemExit) as raised, redirect_stdout(stdout):
                main([command, "--help"])
            self.assertEqual(raised.exception.code, 0)
            self.assertIn("usage:", stdout.getvalue())

    def test_rest_and_mcp_tools_expose_agent_service_operations(self):
        from mythweaver.mcp.server import tool_definitions
        from mythweaver.tools.facade import AgentToolFacade

        facade_tools = {tool["name"] for tool in AgentToolFacade().list_tools()}
        mcp_tools = {tool["name"] for tool in tool_definitions()}
        expected = {
            "search_mods",
            "inspect_mod",
            "compare_mods",
            "verify_mod_list",
            "resolve_mod_list",
            "build_from_list",
            "export_pack",
            "analyze_failure",
        }

        self.assertTrue(expected <= facade_tools)
        self.assertTrue(expected <= mcp_tools)

    def test_mcp_call_tool_dispatches_to_agent_service_method(self):
        from mythweaver.mcp.server import call_tool

        class Facade:
            def __init__(self):
                self.called = None

            async def search_mods(self, **arguments):
                self.called = ("search_mods", arguments)
                return {"results": []}

        facade = Facade()
        result = asyncio.run(call_tool(facade, "search_mods", {"query": "sodium", "loader": "fabric"}))

        self.assertEqual(result, {"results": []})
        self.assertEqual(facade.called, ("search_mods", {"query": "sodium", "loader": "fabric"}))
