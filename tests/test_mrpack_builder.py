import json
import shutil
import unittest
import zipfile
from pathlib import Path

from tests.test_scoring import candidate


TEMP_ROOT = Path.cwd() / "output" / "test-mrpack"


def fresh_case_dir(name: str) -> Path:
    root = (TEMP_ROOT / name).resolve()
    workspace = Path.cwd().resolve()
    if workspace not in root.parents:
        raise RuntimeError(f"refusing to clean path outside workspace: {root}")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return root


class MrpackBuilderTests(unittest.TestCase):
    def test_writes_official_mrpack_index_and_overrides(self):
        from mythweaver.builders.mrpack import build_mrpack, validate_mrpack_archive
        from mythweaver.schemas.contracts import ResolvedPack

        tmp = fresh_case_dir("valid")
        output = tmp / "pack.mrpack"
        override = tmp / "options.txt"
        override.write_text("lang:en_us\n", encoding="utf-8")
        pack = ResolvedPack(
            name="Winter Pack",
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version="0.15.11",
            selected_mods=[candidate("winter1", "Winter", "Snow survival")],
        )

        artifact = build_mrpack(
            pack,
            output,
            overrides={"options.txt": override},
        )

        self.assertEqual(artifact.path, str(output))
        with zipfile.ZipFile(output) as archive:
            self.assertIn("modrinth.index.json", archive.namelist())
            self.assertIn("overrides/options.txt", archive.namelist())
            index = json.loads(archive.read("modrinth.index.json"))
        self.assertEqual(index["formatVersion"], 1)
        self.assertNotEqual(index["versionId"], "0.1.0")
        self.assertTrue(index["versionId"].startswith("winter-pack-"))
        self.assertEqual(index["dependencies"]["minecraft"], "1.20.1")
        self.assertEqual(index["files"][0]["path"], "mods/winter1.jar")
        validate_mrpack_archive(output)

    def test_rejects_unsafe_override_paths(self):
        from mythweaver.builders.mrpack import build_mrpack
        from mythweaver.schemas.contracts import ResolvedPack

        tmp = fresh_case_dir("unsafe")
        override = tmp / "evil.txt"
        override.write_text("bad", encoding="utf-8")
        pack = ResolvedPack(
            name="Unsafe Pack",
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version="0.15.11",
            selected_mods=[],
        )

        with self.assertRaises(ValueError):
            build_mrpack(pack, tmp / "unsafe.mrpack", overrides={"../evil.txt": override})

        with self.assertRaises(ValueError):
            build_mrpack(pack, tmp / "absolute.mrpack", overrides={"/evil.txt": override})

    def test_rejects_unsafe_mod_file_names(self):
        from mythweaver.builders.mrpack import build_mrpack
        from mythweaver.schemas.contracts import ResolvedPack

        bad = candidate("badmod", "Bad", "Unsafe")
        bad.selected_version.files[0].filename = "../bad.jar"
        pack = ResolvedPack(
            name="Unsafe Mod",
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version="0.15.11",
            selected_mods=[bad],
        )

        with self.assertRaises(ValueError):
            build_mrpack(pack, fresh_case_dir("unsafe-mod") / "unsafe.mrpack")

    def test_omits_unknown_env_values_from_mrpack_files(self):
        from mythweaver.builders.mrpack import build_mrpack
        from mythweaver.schemas.contracts import ResolvedPack

        mod = candidate("envmod", "Env", "Unknown side support")
        mod.client_side = "unknown"
        mod.server_side = "unknown"
        tmp = fresh_case_dir("unknown-env")
        pack = ResolvedPack(
            name="Unknown Env",
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version="0.15.11",
            selected_mods=[mod],
        )

        build_mrpack(pack, tmp / "unknown-env.mrpack")

        with zipfile.ZipFile(tmp / "unknown-env.mrpack") as archive:
            index = json.loads(archive.read("modrinth.index.json"))
        self.assertNotIn("env", index["files"][0])


if __name__ == "__main__":
    unittest.main()
