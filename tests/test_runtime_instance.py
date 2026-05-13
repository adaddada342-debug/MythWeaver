import hashlib
import unittest
from pathlib import Path


class RuntimeInstanceTests(unittest.TestCase):
    def test_create_runtime_instance_copies_verified_mods_without_mutating_source(self):
        from mythweaver.runtime.contracts import RuntimeLaunchRequest
        from mythweaver.runtime.instance import create_runtime_instance

        root = Path(".test-output") / "runtime-instance"
        source = root / "source.jar"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"jar")
        before = source.read_bytes()

        instance = create_runtime_instance(
            RuntimeLaunchRequest(
                instance_name="Runtime Pack",
                minecraft_version="1.20.1",
                loader="fabric",
                mod_files=[str(source)],
                output_root=str(root),
            ),
            run_id="abc123",
        )

        copied = Path(instance.mods_dir) / "source.jar"
        self.assertTrue(copied.is_file())
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(hashlib.sha1(copied.read_bytes()).hexdigest(), hashlib.sha1(before).hexdigest())

    def test_create_runtime_instance_rejects_missing_mod_file(self):
        from mythweaver.runtime.contracts import RuntimeLaunchRequest
        from mythweaver.runtime.instance import create_runtime_instance

        with self.assertRaises(FileNotFoundError):
            create_runtime_instance(
                RuntimeLaunchRequest(
                    instance_name="Runtime Pack",
                    minecraft_version="1.20.1",
                    loader="fabric",
                    mod_files=["missing.jar"],
                ),
                run_id="abc123",
            )


if __name__ == "__main__":
    unittest.main()
