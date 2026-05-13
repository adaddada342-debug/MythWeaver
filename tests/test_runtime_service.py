import hashlib
import unittest
from pathlib import Path


class RuntimeServiceTests(unittest.TestCase):
    def test_unsupported_loader_blocks_clearly(self):
        from mythweaver.runtime.contracts import RuntimeLaunchRequest
        from mythweaver.runtime.service import run_runtime_validation

        report = run_runtime_validation(
            RuntimeLaunchRequest(
                instance_name="Forge Pack",
                minecraft_version="1.20.1",
                loader="forge",
                mod_files=[],
                java_path="C:/Java/bin/java.exe",
            ),
            java_major_version_probe=lambda path: 17,
        )

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.issues[0].kind, "unsupported_loader_runtime")

    def test_fixture_backed_fabric_runtime_path_can_pass(self):
        from mythweaver.runtime.contracts import RuntimeLaunchRequest
        from mythweaver.runtime.service import run_runtime_validation

        root = Path(".test-output") / "runtime-service"
        mod = root / "mod.jar"
        helper = root / "mythweaver-smoketest.jar"
        mod.parent.mkdir(parents=True, exist_ok=True)
        mod.write_bytes(b"jar")
        helper.write_bytes(b"helper")
        client = b"client"
        client_sha1 = hashlib.sha1(client).hexdigest()
        payloads = {
            "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json": {
                "versions": [{"id": "1.20.1", "url": "https://example.invalid/version.json"}]
            },
            "https://example.invalid/version.json": {
                "id": "1.20.1",
                "mainClass": "net.minecraft.client.main.Main",
                "downloads": {"client": {"url": "https://example.invalid/client.jar", "sha1": client_sha1}},
                "libraries": [],
                "arguments": {"game": []},
            },
            "https://meta.fabricmc.net/v2/versions/loader": [{"version": "0.15.11", "stable": True}],
            "https://meta.fabricmc.net/v2/versions/loader/1.20.1/0.15.11/profile/json": {
                "mainClass": {"client": "net.fabricmc.loader.impl.launch.knot.KnotClient"},
                "libraries": {"common": []},
            },
        }

        report = run_runtime_validation(
            RuntimeLaunchRequest(
                instance_name="Fabric Pack",
                minecraft_version="1.20.1",
                loader="fabric",
                mod_files=[str(mod)],
                output_root=str(root),
                java_path="C:/Java/bin/java.exe",
                success_grace_seconds=0,
                smoke_test_helper_path=str(helper),
            ),
            fetch_json=lambda url: payloads[url],
            fetch_bytes=lambda url: client if url == "https://example.invalid/client.jar" else b"",
            java_major_version_probe=lambda path: 17,
            process_factory=lambda command: FakeRuntimeProcess(
                "[MythWeaverSmokeTest] CLIENT_READY\n"
                "[MythWeaverSmokeTest] SERVER_STARTED\n"
                "[MythWeaverSmokeTest] PLAYER_JOINED_WORLD\n"
                "[MythWeaverSmokeTest] STABLE_60_SECONDS\n"
            ),
        )

        self.assertEqual(report.status, "passed")
        self.assertTrue(report.instance_path)
        self.assertTrue(report.proof.required_markers_met)
        self.assertTrue((Path(report.instance_path) / "runtime_launch_report.json").is_file())
        self.assertTrue((Path(report.instance_path) / "marker_summary.json").is_file())
        self.assertTrue((Path(report.instance_path) / ".minecraft" / "mods" / "mythweaver-smoketest.jar").is_file())
        self.assertFalse((root / "mythweaver-smoketest.jar").with_name("exported-mythweaver-smoketest.jar").exists())

    def test_missing_helper_when_required_fails_clearly(self):
        from mythweaver.runtime.contracts import RuntimeLaunchRequest
        from mythweaver.runtime.service import run_runtime_validation

        root = Path(".test-output") / "runtime-service-missing-helper"
        mod = root / "mod.jar"
        mod.parent.mkdir(parents=True, exist_ok=True)
        mod.write_bytes(b"jar")
        client = b"client"
        client_sha1 = hashlib.sha1(client).hexdigest()
        payloads = _fabric_payloads(client_sha1)

        report = run_runtime_validation(
            RuntimeLaunchRequest(
                instance_name="Fabric Pack",
                minecraft_version="1.20.1",
                loader="fabric",
                mod_files=[str(mod)],
                output_root=str(root),
                java_path="C:/Java/bin/java.exe",
                success_grace_seconds=0,
                smoke_test_helper_path=str(root / "missing.jar"),
            ),
            fetch_json=lambda url: payloads[url],
            fetch_bytes=lambda url: client if url == "https://example.invalid/client.jar" else b"",
            java_major_version_probe=lambda path: 17,
            process_factory=lambda command: FakeRuntimeProcess(""),
        )

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.issues[0].kind, "smoke_test_helper_missing")

    def test_weak_client_start_signal_does_not_pass_when_proof_required(self):
        from mythweaver.runtime.contracts import RuntimeLaunchRequest
        from mythweaver.runtime.service import run_runtime_validation

        root = Path(".test-output") / "runtime-service-weak"
        mod = root / "mod.jar"
        helper = root / "mythweaver-smoketest.jar"
        mod.parent.mkdir(parents=True, exist_ok=True)
        mod.write_bytes(b"jar")
        helper.write_bytes(b"helper")
        client = b"client"
        client_sha1 = hashlib.sha1(client).hexdigest()
        payloads = _fabric_payloads(client_sha1)

        report = run_runtime_validation(
            RuntimeLaunchRequest(
                instance_name="Fabric Pack",
                minecraft_version="1.20.1",
                loader="fabric",
                mod_files=[str(mod)],
                output_root=str(root),
                java_path="C:/Java/bin/java.exe",
                success_grace_seconds=0,
                smoke_test_helper_path=str(helper),
            ),
            fetch_json=lambda url: payloads[url],
            fetch_bytes=lambda url: client if url == "https://example.invalid/client.jar" else b"",
            java_major_version_probe=lambda path: 17,
            process_factory=lambda command: FakeRuntimeProcess("Sound engine started"),
        )

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.issues[0].kind, "runtime_proof_missing")


class FakeRuntimeProcess:
    returncode = 0

    def __init__(self, stdout: str):
        self.stdout = stdout

    def communicate(self, timeout=None):
        return self.stdout, ""

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def _fabric_payloads(client_sha1):
    return {
        "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json": {
            "versions": [{"id": "1.20.1", "url": "https://example.invalid/version.json"}]
        },
        "https://example.invalid/version.json": {
            "id": "1.20.1",
            "mainClass": "net.minecraft.client.main.Main",
            "downloads": {"client": {"url": "https://example.invalid/client.jar", "sha1": client_sha1}},
            "libraries": [],
            "arguments": {"game": []},
        },
        "https://meta.fabricmc.net/v2/versions/loader": [{"version": "0.15.11", "stable": True}],
        "https://meta.fabricmc.net/v2/versions/loader/1.20.1/0.15.11/profile/json": {
            "mainClass": {"client": "net.fabricmc.loader.impl.launch.knot.KnotClient"},
            "libraries": {"common": []},
        },
    }


if __name__ == "__main__":
    unittest.main()
