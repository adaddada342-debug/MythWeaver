"""Tests for ContentKind mapping, selection normalization, and mrpack path routing."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from mythweaver.builders.mrpack import build_mrpack
from mythweaver.catalog.content_kinds import (
    content_kind_from_curseforge_class_id,
    content_kind_from_modrinth_project_type,
    default_placement_for_kind,
    modrinth_version_uses_loader_filter,
)
from mythweaver.catalog.selection_normalize import normalized_selection_rows
from mythweaver.schemas.contracts import CandidateMod, ModFile, ModVersion, ResolvedPack, SelectedModList


def _fake_mod(project_id: str, *, kind: str = "mod") -> CandidateMod:
    mf = ModFile(
        filename=f"{project_id}.jar",
        url="https://cdn.modrinth.com/data/x/versions/y/z.jar",
        hashes={"sha1": "a" * 40, "sha512": "b" * 128},
        size=100,
        primary=True,
    )
    mv = ModVersion(
        id=f"{project_id}_v",
        project_id=project_id,
        version_number="1.0.0",
        game_versions=["1.20.1"],
        loaders=["fabric"],
        version_type="release",
        status="listed",
        dependencies=[],
        files=[mf],
    )
    return CandidateMod(
        project_id=project_id,
        slug=project_id,
        title=project_id,
        selected_version=mv,
        content_kind=kind,  # type: ignore[arg-type]
        content_placement="manual_world_creation" if kind == "datapack" else None,
    )


class ContentKindLayerTests(unittest.TestCase):
    def test_modrinth_project_type_mapping(self) -> None:
        self.assertEqual(content_kind_from_modrinth_project_type("mod")[0], "mod")
        self.assertEqual(content_kind_from_modrinth_project_type("shader")[0], "shaderpack")
        self.assertEqual(content_kind_from_modrinth_project_type("resourcepack")[0], "resourcepack")
        self.assertEqual(content_kind_from_modrinth_project_type("datapack")[0], "datapack")

    def test_loader_filter_policy(self) -> None:
        self.assertTrue(modrinth_version_uses_loader_filter("mod"))
        self.assertFalse(modrinth_version_uses_loader_filter("datapack"))

    def test_default_placement(self) -> None:
        self.assertEqual(default_placement_for_kind("datapack"), "manual_world_creation")
        self.assertEqual(default_placement_for_kind("mod"), "bundle")

    def test_curseforge_class_mapping(self) -> None:
        self.assertEqual(content_kind_from_curseforge_class_id(6), "mod")
        self.assertEqual(content_kind_from_curseforge_class_id(12), "resourcepack")

    def test_normalize_merges_mods_and_content(self) -> None:
        raw = {
            "name": "t",
            "minecraft_version": "1.20.1",
            "loader": "fabric",
            "mods": [{"slug": "fabric-api", "role": "theme"}],
            "content": [{"slug": "other", "source": "modrinth", "kind": "mod", "required": True}],
        }
        selected = SelectedModList.model_validate(raw)
        rows = normalized_selection_rows(selected)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1].ref, "other")
        self.assertEqual(rows[1].source, "modrinth")

    def test_jjthunder_guidance_trigger(self) -> None:
        from mythweaver.validation.content_export_policy import jjthunder_guidance_lines

        m = _fake_mod("x", kind="mod")
        m.slug = "jjthunder-to-the-max"
        m.title = "JJThunder To The Max"
        lines = jjthunder_guidance_lines([m])
        self.assertTrue(any("JJThunder-style" in line for line in lines))
        self.assertTrue(any("Chunky" in line for line in lines))

        pack = ResolvedPack(
            name="Pack",
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version="0.15.0",
            selected_mods=[
                _fake_mod("m1", kind="mod"),
                _fake_mod("rp1", kind="resourcepack"),
                _fake_mod("dp1", kind="datapack"),
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "p.mrpack"
            build_mrpack(pack, out)
            with zipfile.ZipFile(out) as zf:
                idx = json.loads(zf.read("modrinth.index.json"))
            paths = sorted(f["path"] for f in idx["files"])
        self.assertIn("mods/m1.jar", paths)
        self.assertIn("overrides/resourcepacks/rp1.jar", paths)
        self.assertNotIn("mods/dp1.jar", paths)
        self.assertTrue(all(not p.startswith("mods/dp1") for p in paths))
