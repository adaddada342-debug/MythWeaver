import json
import shutil
import unittest
import zipfile
from pathlib import Path


TEMP_ROOT = Path(".test-output") / "test-cf-manifest"


def fresh_dir(name: str) -> Path:
    root = (TEMP_ROOT / name).resolve()
    workspace = Path.cwd().resolve()
    if workspace not in root.parents:
        raise RuntimeError(f"refusing to clean path outside workspace: {root}")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return root


def cf_candidate(**overrides):
    from mythweaver.schemas.contracts import SourceFileCandidate

    data = {
        "source": "curseforge",
        "project_id": "123",
        "file_id": "456",
        "name": "Curse Mod",
        "file_name": "curse.jar",
        "acquisition_status": "verified_manual_required",
    }
    data.update(overrides)
    return SourceFileCandidate(**data)


class CurseForgeManifestBuilderTests(unittest.TestCase):
    def test_writes_valid_manifest_zip(self):
        from mythweaver.builders.curseforge_manifest import build_curseforge_manifest
        from mythweaver.schemas.contracts import SourceResolveReport

        root = fresh_dir("valid")
        report = SourceResolveReport(
            status="resolved",
            minecraft_version="1.20.1",
            loader="forge",
            manifest_files=[cf_candidate()],
            export_supported=True,
        )

        artifact = build_curseforge_manifest(
            report,
            root / "pack.zip",
            name="Curse Pack",
            version="1.0.0",
            loader_version="47.2.0",
        )

        self.assertEqual(artifact.kind, "curseforge-manifest")
        with zipfile.ZipFile(root / "pack.zip") as archive:
            self.assertIn("manifest.json", archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["manifestType"], "minecraftModpack")
        self.assertEqual(manifest["minecraft"]["modLoaders"][0]["id"], "forge-47.2.0")
        self.assertEqual(manifest["files"], [{"projectID": 123, "fileID": 456, "required": True}])

    def test_rejects_modrinth_candidates_and_missing_file_id(self):
        from mythweaver.builders.curseforge_manifest import build_curseforge_manifest
        from mythweaver.schemas.contracts import SourceResolveReport

        root = fresh_dir("rejects")
        with self.assertRaises(ValueError):
            build_curseforge_manifest(
                SourceResolveReport(
                    status="resolved",
                    minecraft_version="1.20.1",
                    loader="forge",
                    manifest_files=[cf_candidate(source="modrinth")],
                ),
                root / "bad-source.zip",
            )
        with self.assertRaises(ValueError):
            build_curseforge_manifest(
                SourceResolveReport(
                    status="resolved",
                    minecraft_version="1.20.1",
                    loader="forge",
                    manifest_files=[cf_candidate(file_id=None)],
                ),
                root / "bad-file.zip",
            )

    def test_rejects_unsupported_curseforge_candidate(self):
        from mythweaver.builders.curseforge_manifest import build_curseforge_manifest
        from mythweaver.schemas.contracts import SourceResolveReport

        root = fresh_dir("unsupported")
        with self.assertRaises(ValueError):
            build_curseforge_manifest(
                SourceResolveReport(
                    status="resolved",
                    minecraft_version="1.20.1",
                    loader="forge",
                    manifest_files=[cf_candidate(acquisition_status="unsupported")],
                ),
                root / "bad-status.zip",
            )

    def test_preserves_overrides_safely(self):
        from mythweaver.builders.curseforge_manifest import build_curseforge_manifest
        from mythweaver.schemas.contracts import SourceResolveReport

        root = fresh_dir("overrides")
        override = root / "options.txt"
        override.write_text("lang:en_us\n", encoding="utf-8")
        report = SourceResolveReport(
            status="resolved",
            minecraft_version="1.20.1",
            loader="fabric",
            manifest_files=[cf_candidate()],
        )

        build_curseforge_manifest(
            report,
            root / "pack.zip",
            overrides={"config/options.txt": override},
            loader_version="0.15.11",
        )

        with zipfile.ZipFile(root / "pack.zip") as archive:
            self.assertIn("overrides/config/options.txt", archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["minecraft"]["modLoaders"][0]["id"], "fabric-0.15.11")
        with self.assertRaises(ValueError):
            build_curseforge_manifest(report, root / "unsafe.zip", overrides={"../evil.txt": override})


if __name__ == "__main__":
    unittest.main()
