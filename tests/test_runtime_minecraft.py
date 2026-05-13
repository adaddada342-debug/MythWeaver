import hashlib
import unittest
from pathlib import Path


class RuntimeMinecraftTests(unittest.TestCase):
    def test_prepare_minecraft_client_uses_fixture_manifest_and_verifies_sha1(self):
        from mythweaver.runtime.minecraft import prepare_minecraft_client

        client_bytes = b"client"
        library_bytes = b"library"
        asset_bytes = b"asset"
        client_sha1 = hashlib.sha1(client_bytes).hexdigest()
        library_sha1 = hashlib.sha1(library_bytes).hexdigest()
        asset_sha1 = hashlib.sha1(asset_bytes).hexdigest()
        payloads = {
            "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json": {
                "versions": [{"id": "1.20.1", "url": "https://example.invalid/1.20.1.json"}]
            },
            "https://example.invalid/1.20.1.json": {
                "id": "1.20.1",
                "mainClass": "net.minecraft.client.main.Main",
                "assetIndex": {"id": "5", "url": "https://example.invalid/assets.json"},
                "downloads": {"client": {"url": "https://example.invalid/client.jar", "sha1": client_sha1}},
                "libraries": [
                    {
                        "downloads": {
                            "artifact": {
                                "path": "com/example/lib/1.0/lib-1.0.jar",
                                "url": "https://example.invalid/lib.jar",
                                "sha1": library_sha1,
                            }
                        }
                    }
                ],
                "arguments": {"game": ["--demo"]},
            },
            "https://example.invalid/assets.json": {
                "objects": {"minecraft/lang/en_us.json": {"hash": asset_sha1, "size": len(asset_bytes)}}
            },
        }
        bytes_by_url = {
            "https://example.invalid/client.jar": client_bytes,
            "https://example.invalid/lib.jar": library_bytes,
            f"https://resources.download.minecraft.net/{asset_sha1[:2]}/{asset_sha1}": asset_bytes,
        }

        runtime = prepare_minecraft_client(
            "1.20.1",
            Path(".test-output") / "mc-cache",
            fetch_json=lambda url: payloads[url],
            fetch_bytes=lambda url: bytes_by_url[url],
        )

        self.assertEqual(runtime.version_id, "1.20.1")
        self.assertTrue(Path(runtime.client_jar).is_file())
        self.assertEqual(runtime.main_class, "net.minecraft.client.main.Main")
        self.assertIn("--demo", runtime.game_arguments)


if __name__ == "__main__":
    unittest.main()
