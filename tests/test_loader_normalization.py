import unittest


class LoaderNormalizationTests(unittest.TestCase):
    def test_loader_aliases_normalize_to_canonical_values(self):
        from mythweaver.catalog.loaders import normalize_loader

        cases = {
            "neo forge": "neoforge",
            "neo-forge": "neoforge",
            "fabric loader": "fabric",
            "minecraft forge": "forge",
            "Legacy Fabric": "legacy_fabric",
            "unknown thing": "unknown",
        }

        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_loader(value), expected)

    def test_loader_mappings_for_source_and_launcher_names(self):
        from mythweaver.catalog.loaders import (
            curseforge_loader_name,
            is_modded_loader,
            modrinth_loader_category,
            prism_component_uid,
        )

        self.assertTrue(is_modded_loader("fabric loader"))
        self.assertFalse(is_modded_loader("vanilla"))
        self.assertEqual(curseforge_loader_name("neo forge"), "NeoForge")
        self.assertEqual(prism_component_uid("fabric"), "net.fabricmc.fabric-loader")
        self.assertEqual(modrinth_loader_category("minecraft forge"), "forge")
        self.assertIsNone(prism_component_uid("unknown thing"))

    def test_builders_refuse_unknown_loader_when_exact_id_is_required(self):
        from mythweaver.builders.curseforge_manifest import build_curseforge_manifest
        from mythweaver.builders.mrpack import build_mrpack
        from mythweaver.schemas.contracts import ResolvedPack, SourceResolveReport

        with self.assertRaises(ValueError):
            build_curseforge_manifest(
                SourceResolveReport(status="resolved", minecraft_version="1.20.1", loader="unknown"),
                __import__("pathlib").Path.cwd() / "output" / "unknown.zip",
            )
        with self.assertRaises(ValueError):
            build_mrpack(
                ResolvedPack(name="Unknown", minecraft_version="1.20.1", loader="unknown", loader_version="1.0.0"),
                __import__("pathlib").Path.cwd() / "output" / "unknown.mrpack",
            )


if __name__ == "__main__":
    unittest.main()
