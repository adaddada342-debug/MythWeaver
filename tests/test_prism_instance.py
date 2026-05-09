import json
import unittest
from pathlib import Path

from tests.test_scoring import candidate


class PrismInstanceBuilderTests(unittest.TestCase):
    def test_writes_prism_instance_metadata_and_mod_files(self):
        from mythweaver.builders.prism_instance import build_prism_instance
        from mythweaver.schemas.contracts import ResolvedPack

        root = Path.cwd() / "output" / "test-prism-instance"
        pack = ResolvedPack(
            name="Winter Pack",
            minecraft_version="1.20.1",
            loader="fabric",
            loader_version="0.15.11",
            selected_mods=[candidate("winter1", "Winter", "Snow survival")],
        )
        cached_mod = root / "cache" / "winter1.jar"
        cached_mod.parent.mkdir(parents=True, exist_ok=True)
        cached_mod.write_bytes(b"jar")

        artifact = build_prism_instance(
            pack,
            root / "instances",
            downloaded_files={"winter1": cached_mod},
        )

        instance_dir = Path(artifact.path)
        self.assertTrue((instance_dir / "instance.cfg").is_file())
        self.assertTrue((instance_dir / ".minecraft" / "mods" / "winter1.jar").is_file())
        mmc_pack = json.loads((instance_dir / "mmc-pack.json").read_text(encoding="utf-8"))
        self.assertEqual(mmc_pack["components"][0]["uid"], "net.minecraft")


if __name__ == "__main__":
    unittest.main()
