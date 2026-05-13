import unittest
from pathlib import Path


class RuntimeLoaderInstallTests(unittest.TestCase):
    def test_fabric_loader_profile_uses_fixture_metadata(self):
        from mythweaver.runtime.loader_install import install_loader_runtime

        payloads = {
            "https://meta.fabricmc.net/v2/versions/loader": [
                {"version": "0.15.11", "stable": True},
                {"version": "0.16.0", "stable": False},
            ],
            "https://meta.fabricmc.net/v2/versions/loader/1.20.1/0.15.11/profile/json": {
                "mainClass": {"client": "net.fabricmc.loader.impl.launch.knot.KnotClient"},
                "libraries": {"common": [{"name": "net.fabricmc:fabric-loader:0.15.11", "url": "https://maven.fabricmc.net/"}]},
            },
        }

        def fetch_json(url: str):
            return payloads[url]

        result = install_loader_runtime(
            "fabric",
            "1.20.1",
            Path(".test-output") / "loader-cache",
            fetch_json=fetch_json,
            fetch_bytes=lambda url: b"jar",
        )

        self.assertFalse(result.issues)
        self.assertEqual(result.runtime.loader_version, "0.15.11")
        self.assertEqual(result.runtime.main_class, "net.fabricmc.loader.impl.launch.knot.KnotClient")

    def test_unsupported_loader_returns_issue(self):
        from mythweaver.runtime.loader_install import install_loader_runtime

        result = install_loader_runtime("forge", "1.20.1", Path(".test-output") / "loader-cache")

        self.assertIsNone(result.runtime)
        self.assertEqual(result.issues[0].kind, "unsupported_loader_runtime")


if __name__ == "__main__":
    unittest.main()
