"""Regression tests for Autopilot / resolver source provider wiring (offline)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport


class ResolverCurseForgeWiringTests(unittest.TestCase):
    def test_provider_for_source_curseforge_reads_env_when_api_key_omitted(self):
        from mythweaver.sources.resolver import provider_for_source

        with patch.dict("os.environ", {"CURSEFORGE_API_KEY": "test-key-from-env"}, clear=False):
            provider = provider_for_source("curseforge", modrinth=None)
        self.assertTrue(provider.is_configured())

    def test_provider_for_source_curseforge_explicit_none_uses_env(self):
        from mythweaver.sources.resolver import provider_for_source

        with patch.dict("os.environ", {"CURSEFORGE_API_KEY": "explicit-none-path"}, clear=False):
            provider = provider_for_source("curseforge", modrinth=None, curseforge_api_key=None)
        self.assertTrue(provider.is_configured())

    def test_provider_for_source_curseforge_missing_env_not_configured(self):
        from mythweaver.sources.resolver import provider_for_source

        with patch.dict("os.environ", {"CURSEFORGE_API_KEY": ""}):
            provider = provider_for_source("curseforge", modrinth=None, curseforge_api_key=None)
        self.assertFalse(provider.is_configured())

    def test_provider_for_source_curseforge_explicit_key_overrides_env(self):
        from mythweaver.sources.curseforge import CurseForgeSourceProvider
        from mythweaver.sources.resolver import provider_for_source

        with patch.dict("os.environ", {"CURSEFORGE_API_KEY": "from-env"}, clear=False):
            provider = provider_for_source("curseforge", modrinth=None, curseforge_api_key="override-key")
        self.assertIsInstance(provider, CurseForgeSourceProvider)
        self.assertEqual(provider.api_key, "override-key")


class ModrinthProviderWiringTests(unittest.TestCase):
    def test_modrinth_source_provider_configured_when_client_passed(self):
        from mythweaver.sources.modrinth import ModrinthSourceProvider

        self.assertTrue(ModrinthSourceProvider(object()).is_configured())
        self.assertFalse(ModrinthSourceProvider(None).is_configured())


class AutopilotModrinthInjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_autopilot_passes_modrinth_into_resolve_sources(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.loop import run_autopilot

        root = Path(".test-output") / "autopilot-source-wiring"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(
                name="Wiring Pack",
                minecraft_version="1.20.1",
                loader="fabric",
                mods=[{"slug": "sodium", "role": "foundation", "reason_selected": "test"}],
            ).model_dump_json(),
            encoding="utf-8",
        )

        captured: dict[str, object | None] = {}

        async def spy_resolve(selected, **kwargs):
            if not captured:
                captured["modrinth"] = kwargs.get("modrinth")
            return SourceResolveReport(
                status="failed",
                minecraft_version=kwargs["minecraft_version"],
                loader=kwargs["loader"],
                export_supported=False,
                export_blockers=["synthetic blocked for wiring test"],
            )

        with patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", spy_resolve):
            report = await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    sources=["modrinth"],
                    minecraft_version="1.20.1",
                    loader="fabric",
                    output_root=str(root),
                    max_attempts=1,
                )
            )

        self.assertIsNotNone(captured.get("modrinth"), "resolve_sources_for_selected_mods should receive modrinth client")
        self.assertEqual(report.status, "blocked")

    async def test_build_target_matrix_receives_modrinth_when_autopilot_negotiates(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.loop import run_autopilot

        root = Path(".test-output") / "autopilot-matrix-wiring"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(
                name="Matrix Wiring Pack",
                minecraft_version="any",
                loader="fabric",
                mods=[{"slug": "sodium", "role": "foundation", "reason_selected": "test"}],
            ).model_dump_json(),
            encoding="utf-8",
        )

        matrix_modrinth: list[object | None] = []

        async def fake_matrix(selected, **kwargs):
            matrix_modrinth.append(kwargs.get("modrinth"))
            from mythweaver.catalog.target_matrix import DEFAULT_LOADERS
            from mythweaver.schemas.contracts import TargetCandidate, TargetMatrixReport

            candidate = TargetCandidate(
                minecraft_version="1.20.1",
                loader="fabric",
                sources=list(kwargs.get("sources", [])),
                score=1.0,
            )
            return TargetMatrixReport(
                requested_minecraft_version=selected.minecraft_version,
                requested_loader=str(selected.loader),
                considered_versions=["1.20.1"],
                considered_loaders=[name for name in DEFAULT_LOADERS if name == "fabric"],
                best=candidate,
                candidates=[candidate],
                status="resolved",
                warnings=[],
            )

        async def spy_resolve(selected, **kwargs):
            return SourceResolveReport(
                status="failed",
                minecraft_version=kwargs["minecraft_version"],
                loader=kwargs["loader"],
                export_supported=False,
                export_blockers=["stop after resolve for test"],
            )

        with (
            patch("mythweaver.autopilot.loop.build_target_matrix", fake_matrix),
            patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", spy_resolve),
        ):
            await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    sources=["modrinth"],
                    minecraft_version="auto",
                    loader="fabric",
                    output_root=str(root),
                    max_attempts=1,
                )
            )

        self.assertEqual(len(matrix_modrinth), 1)
        self.assertIsNotNone(matrix_modrinth[0], "build_target_matrix should receive modrinth client")
