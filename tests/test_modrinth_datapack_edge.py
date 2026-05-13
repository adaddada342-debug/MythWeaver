"""Modrinth project_type mod + datapack-only version file (narrow edge path)."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from mythweaver.builders.mrpack import build_mrpack
from mythweaver.builders.prism_instance import build_prism_instance
from mythweaver.catalog.modrinth_datapack_edge import (
    PLATFORM_MOD_DATAPACK_FILE_WARNING,
    apply_modrinth_mod_datapack_edge_to_candidate,
    first_installable_modrinth_version_dict,
    modrinth_mod_project_datapack_edge_applies,
    modrinth_version_loaders_effectively_datapack_only,
)
from mythweaver.modrinth.client import candidate_from_project_hit
from mythweaver.pipeline.agent_service import _installability_details
from mythweaver.schemas.contracts import CandidateMod, ModFile, ModVersion, ResolvedPack
from mythweaver.validation.content_export_policy import collect_content_export_warnings, jjthunder_guidance_lines


def _file_zip(name: str = "p.zip") -> dict:
    return {
        "filename": name,
        "primary": True,
        "url": "https://cdn.modrinth.com/data/x/versions/y/z.zip",
        "hashes": {"sha1": "a" * 40, "sha512": "b" * 128},
        "size": 10,
    }


def _version(*, vid: str, pid: str, loaders: list[str], fn: str = "p.zip") -> dict:
    return {
        "id": vid,
        "project_id": pid,
        "version_number": "1.0.0",
        "loaders": loaders,
        "game_versions": ["1.20.1"],
        "status": "listed",
        "dependencies": [],
        "files": [_file_zip(fn)],
    }


def _hit(*, slug: str, title: str, pid: str, project_type: str = "mod") -> dict:
    return {
        "project_type": project_type,
        "status": "listed",
        "slug": slug,
        "title": title,
        "id": pid,
        "project_id": pid,
        "versions": ["1.20.1"],
        "description": "",
        "categories": [],
        "downloads": 0,
        "follows": 0,
        "client_side": "unknown",
        "server_side": "unknown",
    }


class ModrinthDatapackEdgeTests(unittest.TestCase):
    def test_datapack_only_loaders_detected(self) -> None:
        self.assertTrue(modrinth_version_loaders_effectively_datapack_only(_version(vid="a", pid="p", loaders=["datapack"])))
        self.assertFalse(modrinth_version_loaders_effectively_datapack_only(_version(vid="b", pid="p", loaders=["fabric"])))
        self.assertFalse(modrinth_version_loaders_effectively_datapack_only(_version(vid="c", pid="p", loaders=[])))

    def test_edge_applies_only_mod_project(self) -> None:
        v = _version(vid="v", pid="p", loaders=["datapack"])
        self.assertTrue(modrinth_mod_project_datapack_edge_applies(project_type="mod", version=v))
        self.assertFalse(modrinth_mod_project_datapack_edge_applies(project_type="datapack", version=v))

    def test_installability_mod_project_datapack_file(self) -> None:
        pid = "proj1"
        hit = _hit(slug="jjthunder-to-the-max", title="JJThunder To The Max", pid=pid)
        ver = _version(vid="vx", pid=pid, loaders=["datapack"])
        d = _installability_details(hit, [ver], loader="fabric", minecraft_version="1.20.1", require_loader_match=True)
        self.assertIsNotNone(d["candidate"])
        self.assertEqual(d["selected_version"], ver)
        c = apply_modrinth_mod_datapack_edge_to_candidate(d["candidate"], ver)
        self.assertEqual(c.content_kind, "datapack")
        self.assertEqual(c.content_placement, "manual_world_creation")
        self.assertEqual(c.platform_project_type, "mod")
        self.assertIn(PLATFORM_MOD_DATAPACK_FILE_WARNING, c.why_selected)

    def test_fabric_mod_row_stays_mod(self) -> None:
        pid = "proj2"
        hit = _hit(slug="fabric-api", title="Fabric API", pid=pid)
        ver = _version(vid="vf", pid=pid, loaders=["fabric"], fn="api.jar")
        d = _installability_details(hit, [ver], loader="fabric", minecraft_version="1.20.1", require_loader_match=True)
        self.assertIsNotNone(d["candidate"])
        c = apply_modrinth_mod_datapack_edge_to_candidate(d["candidate"], ver)
        self.assertEqual(c.content_kind, "mod")
        self.assertFalse(modrinth_mod_project_datapack_edge_applies(project_type="mod", version=ver))

    def test_mixed_versions_prefers_fabric_first(self) -> None:
        pid = "mix"
        hit = _hit(slug="mixed", title="Mixed", pid=pid)
        v_dp = _version(vid="dp", pid=pid, loaders=["datapack"], fn="d.zip")
        v_fb = _version(vid="fb", pid=pid, loaders=["fabric"], fn="m.jar")
        chosen = first_installable_modrinth_version_dict(
            hit, [v_dp, v_fb], loader="fabric", minecraft_version="1.20.1", require_loader_match=True
        )
        self.assertEqual(chosen, v_fb)
        chosen2 = first_installable_modrinth_version_dict(
            hit, [v_fb, v_dp], loader="fabric", minecraft_version="1.20.1", require_loader_match=True
        )
        self.assertEqual(chosen2, v_fb)

    def test_mrpack_omits_manual_datapack_edge(self) -> None:
        pid = "jj"
        hit = _hit(slug="jjthunder-to-the-max", title="JJThunder To The Max", pid=pid)
        ver = _version(vid="vjj", pid=pid, loaders=["datapack"])
        base = candidate_from_project_hit(hit, ver)
        mod = apply_modrinth_mod_datapack_edge_to_candidate(base, ver)
        pack = ResolvedPack(
            name="Edge",
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version="0.15.0",
            selected_mods=[mod],
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "e.mrpack"
            build_mrpack(pack, out)
            with zipfile.ZipFile(out) as zf:
                idx = json.loads(zf.read("modrinth.index.json"))
        self.assertEqual(idx["files"], [])

    def test_prism_skips_manual_datapack_edge(self) -> None:
        pid = "jj2"
        hit = _hit(slug="x", title="X", pid=pid)
        ver = _version(vid="v", pid=pid, loaders=["datapack"])
        base = candidate_from_project_hit(hit, ver)
        mod = apply_modrinth_mod_datapack_edge_to_candidate(base, ver)
        pack = ResolvedPack(
            name="PrismEdge",
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version="0.15.0",
            selected_mods=[mod],
        )
        with tempfile.TemporaryDirectory() as tmp:
            inst = Path(tmp) / "instances"
            art = build_prism_instance(pack, inst, downloaded_files={})
            mods_dir = Path(art.path) / ".minecraft" / "mods"
            self.assertTrue(mods_dir.is_dir())
            self.assertEqual(list(mods_dir.iterdir()), [])

    def test_export_warnings_include_platform_mismatch(self) -> None:
        pid = "jj3"
        hit = _hit(slug="s", title="S", pid=pid)
        ver = _version(vid="v", pid=pid, loaders=["datapack"])
        mod = apply_modrinth_mod_datapack_edge_to_candidate(candidate_from_project_hit(hit, ver), ver)
        w = collect_content_export_warnings([mod])
        self.assertIn(PLATFORM_MOD_DATAPACK_FILE_WARNING, w)

    def test_jjthunder_guidance_extended(self) -> None:
        mf = ModFile(
            filename="x.zip",
            url="https://cdn.modrinth.com/data/x/versions/y/z.zip",
            hashes={"sha1": "a" * 40, "sha512": "b" * 128},
            size=10,
            primary=True,
        )
        mv = ModVersion(
            id="v",
            project_id="p",
            version_number="1",
            game_versions=["1.20.1"],
            loaders=["datapack"],
            version_type="release",
            status="listed",
            dependencies=[],
            files=[mf],
        )
        m = CandidateMod(
            project_id="p",
            slug="jjthunder-to-the-max",
            title="JJThunder To The Max",
            selected_version=mv,
            content_kind="datapack",
            content_placement="manual_world_creation",
        )
        lines = jjthunder_guidance_lines([m])
        blob = "\n".join(lines).lower()
        self.assertIn("jjthunder-style", blob)
        self.assertIn("terralith", blob)
        self.assertIn("chunky", blob)
        self.assertIn("render distance", blob)
        self.assertIn("simulation distance", blob)
        self.assertIn("shaders", blob)
