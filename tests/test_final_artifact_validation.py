"""Tests for final JAR/fabric.mod.json artifact validation."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.test_scoring import candidate


def _write_fabric_mod_jar(
    path: Path,
    *,
    mod_id: str,
    minecraft_dep: str | list[str],
    name: str | None = None,
) -> None:
    fm = {
        "schemaVersion": 1,
        "id": mod_id,
        "version": "1.0.0",
        "name": name or mod_id.title(),
        "depends": {"minecraft": minecraft_dep, "fabricloader": ">=0.14"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("fabric.mod.json", json.dumps(fm))


class FinalArtifactValidationTests(unittest.TestCase):
    def test_duplicate_fabric_mod_id_collapses_to_one_row(self):
        from mythweaver.schemas.contracts import ResolvedPack
        from mythweaver.validation.final_artifact_validation import validate_and_filter_resolved_pack

        a = candidate("keep_me", "Keep", "desc")
        b = candidate("drop_me", "Drop", "desc")
        b.selection_type = "dependency_added"

        pack = ResolvedPack(
            name="t",
            minecraft_version="1.20.1",
            loader="fabric",
            selected_mods=[a, b],
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ja = base / "a.jar"
            jb = base / "b.jar"
            _write_fabric_mod_jar(ja, mod_id="dup_id", minecraft_dep=">=1.20.1")
            _write_fabric_mod_jar(jb, mod_id="dup_id", minecraft_dep=">=1.20.1")
            files = {a.project_id: ja, b.project_id: jb}

            new_pack, new_files, report, ok = validate_and_filter_resolved_pack(
                pack,
                files,
                prefer_project_ids=frozenset({a.project_id}),
                target_minecraft="1.20.1",
            )

        self.assertTrue(ok)
        self.assertEqual(len(new_pack.selected_mods), 1)
        self.assertEqual(new_pack.selected_mods[0].project_id, "keep_me")
        self.assertEqual(len(report["duplicate_mod_ids"]), 1)
        self.assertEqual(len(report["removed_duplicate_jars"]), 1)
        self.assertIn("keep_me", new_files)
        self.assertNotIn("drop_me", new_files)

    def test_wrong_minecraft_dep_blocks_jar(self):
        from mythweaver.schemas.contracts import ResolvedPack
        from mythweaver.validation.final_artifact_validation import validate_and_filter_resolved_pack

        m = candidate("bad_mc", "Bad MC", "desc")
        pack = ResolvedPack(
            name="t",
            minecraft_version="1.20.1",
            loader="fabric",
            selected_mods=[m],
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            jar = base / "bad.jar"
            _write_fabric_mod_jar(jar, mod_id="bad_mc", minecraft_dep=">=1.21")
            new_pack, _new_files, report, ok = validate_and_filter_resolved_pack(
                pack,
                {m.project_id: jar},
                prefer_project_ids=frozenset(),
                target_minecraft="1.20.1",
            )

        self.assertFalse(ok)
        self.assertEqual(len(new_pack.selected_mods), 0)
        self.assertTrue(any(b.get("reason") == "fabric_dep_minecraft_range_excludes_target" for b in report["blocked_jars"]))
        self.assertTrue(report["wrong_minecraft_version_jars"])

    def test_curated_blocklist_blocks_jar(self):
        from mythweaver.schemas.contracts import ResolvedPack
        from mythweaver.validation.final_artifact_validation import validate_and_filter_resolved_pack

        good = candidate("good_mod", "Good", "desc")
        bad = candidate("nf", "Nofab", "desc")
        bad.slug = "nofabric"
        pack = ResolvedPack(
            name="t", minecraft_version="1.20.1", loader="fabric", selected_mods=[good, bad],
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            jg = base / "good.jar"
            jb = base / "nf.jar"
            _write_fabric_mod_jar(jg, mod_id="good_mod", minecraft_dep=">=1.20.1")
            _write_fabric_mod_jar(jb, mod_id="something_else", minecraft_dep=">=1.20.1")
            new_pack, _nf, report, ok = validate_and_filter_resolved_pack(
                pack,
                {good.project_id: jg, bad.project_id: jb},
                prefer_project_ids=frozenset(),
                target_minecraft="1.20.1",
            )

        self.assertTrue(ok)
        self.assertEqual({m.project_id for m in new_pack.selected_mods}, {"good_mod"})
        self.assertTrue(any(b.get("reason") == "artifact_slug_curated_blocklist" for b in report["blocked_jars"]))

    def test_missing_download_fails(self):
        from mythweaver.schemas.contracts import ResolvedPack
        from mythweaver.validation.final_artifact_validation import validate_and_filter_resolved_pack

        m = candidate("only", "Only", "desc")
        pack = ResolvedPack(name="t", minecraft_version="1.20.1", loader="fabric", selected_mods=[m])
        new_pack, _files, report, ok = validate_and_filter_resolved_pack(
            pack,
            {},
            prefer_project_ids=frozenset(),
            target_minecraft="1.20.1",
        )
        self.assertFalse(ok)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(report["missing_downloaded_jars"])
        self.assertEqual(len(new_pack.selected_mods), 0)


class ShallowSearchBlockedTests(unittest.TestCase):
    def test_blocks_hack_slug(self):
        from mythweaver.knowledge.fabric_artifact_policy import shallow_search_blocked

        self.assertEqual(shallow_search_blocked(slug="evil-hacks", title="Evil", version_number="1.0.0"), "filter_keyword_hack")

    def test_blocks_placeholder_version(self):
        from mythweaver.knowledge.fabric_artifact_policy import shallow_search_blocked

        self.assertEqual(shallow_search_blocked(slug="tiny", title="Tiny", version_number="0.0.1"), "filter_placeholder_version")


if __name__ == "__main__":
    unittest.main()
