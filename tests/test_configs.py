import json
import unittest
from pathlib import Path


class ConfigGeneratorTests(unittest.TestCase):
    def test_generates_datapack_with_pack_mcmeta_and_lore_function(self):
        from mythweaver.configs.datapack import generate_lore_datapack
        from mythweaver.schemas.contracts import RequirementProfile

        root = Path.cwd() / "output" / "test-datapack"
        if root.exists():
            for file in sorted(root.rglob("*"), reverse=True):
                if file.is_file():
                    file.unlink()
                elif file.is_dir():
                    file.rmdir()
        profile = RequirementProfile(
            name="Infinite Winter",
            themes=["winter", "horror"],
            mood=["isolated"],
        )

        artifact = generate_lore_datapack(profile, root)

        pack_meta = json.loads((root / "pack.mcmeta").read_text(encoding="utf-8"))
        self.assertEqual(artifact.kind, "datapack")
        self.assertEqual(pack_meta["pack"]["pack_format"], 15)
        self.assertTrue((root / "data" / "mythweaver" / "functions" / "intro.mcfunction").is_file())

    def test_escapes_lore_text_in_mcfunction_json(self):
        from mythweaver.configs.datapack import generate_lore_datapack
        from mythweaver.schemas.contracts import RequirementProfile

        root = Path.cwd() / "output" / "test-datapack-escaping"
        profile = RequirementProfile(name='Winter "Night"', themes=['ice "storm"'])

        generate_lore_datapack(profile, root)

        function_lines = (
            root / "data" / "mythweaver" / "functions" / "intro.mcfunction"
        ).read_text(encoding="utf-8").splitlines()
        for line in function_lines:
            payload = line.removeprefix("tellraw @a ")
            json.loads(payload)


if __name__ == "__main__":
    unittest.main()
