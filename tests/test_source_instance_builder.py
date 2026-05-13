import hashlib
import shutil
import unittest
from pathlib import Path


class SourceInstanceBuilderTests(unittest.TestCase):
    def test_local_instance_allows_local_verified_jars(self):
        from mythweaver.builders.source_instance import build_source_instance
        from mythweaver.schemas.contracts import SourceFileCandidate, SourceResolveReport

        root = (Path.cwd() / ".test-output" / "source-instance").resolve()
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        jar = root / "local.jar"
        jar.write_bytes(b"jar")
        sha1 = hashlib.sha1(b"jar").hexdigest()

        report = SourceResolveReport(
            status="resolved",
            minecraft_version="1.20.1",
            loader="fabric",
            selected_files=[
                SourceFileCandidate(
                    source="local",
                    name="Local",
                    file_name="local.jar",
                    download_url=str(jar),
                    hashes={"sha1": sha1},
                    acquisition_status="verified_auto",
                )
            ],
            export_supported=True,
            dependency_closure_passed=True,
        )

        artifact = build_source_instance(report, root / "instances", name="Local Pack", prism=False)

        self.assertEqual(artifact.kind, "local-instance")
        self.assertTrue((Path(artifact.path) / ".minecraft" / "mods" / "local.jar").is_file())

    def test_local_instance_rejects_unrecognized_hash_algorithms(self):
        from mythweaver.builders.source_instance import build_source_instance
        from mythweaver.schemas.contracts import SourceFileCandidate, SourceResolveReport

        root = (Path.cwd() / ".test-output" / "source-instance-bad-hash").resolve()
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        jar = root / "local.jar"
        jar.write_bytes(b"jar")

        report = SourceResolveReport(
            status="resolved",
            minecraft_version="1.20.1",
            loader="fabric",
            selected_files=[
                SourceFileCandidate(
                    source="local",
                    name="Local",
                    file_name="local.jar",
                    download_url=str(jar),
                    hashes={"sha256": "0" * 64},
                    acquisition_status="verified_auto",
                )
            ],
            export_supported=True,
            dependency_closure_passed=True,
        )

        with self.assertRaises(ValueError):
            build_source_instance(report, root / "instances", name="Local Pack", prism=False)


if __name__ == "__main__":
    unittest.main()
