import unittest


class RuntimeDiagnosisTests(unittest.TestCase):
    def test_missing_fabric_api_dependency_is_high_confidence(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("ModResolutionException: Mod cameraoverhaul requires mod fabric-api")

        self.assertEqual(diagnoses[0].kind, "missing_fabric_api")
        self.assertEqual(diagnoses[0].confidence, "high")
        self.assertIn("fabric-api", diagnoses[0].affected_mod_ids)
        self.assertIn("add_mod", diagnoses[0].suggested_repair_action_kinds)

    def test_generic_missing_dependency_extracts_mod_id(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("Could not find required mod: architectury")

        self.assertEqual(diagnoses[0].kind, "missing_dependency")
        self.assertEqual(diagnoses[0].confidence, "high")
        self.assertIn("architectury", diagnoses[0].affected_mod_ids)

    def test_forge_mod_in_fabric_runtime_is_wrong_loader_without_safe_repair(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("Mod xyz requires forge 47.2.0 but Fabric Loader is present")

        self.assertIn(diagnoses[0].kind, {"loader_mismatch", "unsupported_loader_runtime"})
        self.assertNotIn("add_mod", diagnoses[0].suggested_repair_action_kinds)

    def test_java_class_major_version_error(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("UnsupportedClassVersionError class file version 65.0")

        self.assertEqual(diagnoses[0].kind, "java_version_mismatch")

    def test_mixin_apply_failure(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("Mixin apply failed: InvalidMixinException in renderer")

        self.assertEqual(diagnoses[0].kind, "mixin_failure")

    def test_duplicate_mod_id(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("DuplicateModsFoundException: Duplicate mod id sodium")

        self.assertIn(diagnoses[0].kind, {"duplicate_mod", "mod_id_conflict"})
        self.assertIn("sodium", diagnoses[0].affected_mod_ids)

    def test_config_parse_error(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("Failed loading config file example.toml: ParsingException")

        self.assertEqual(diagnoses[0].kind, "config_parse_error")
        self.assertIn("example.toml", diagnoses[0].affected_files)

    def test_access_widener_failure(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("AccessWidenerFormatException: error reading access widener")

        self.assertEqual(diagnoses[0].kind, "access_widener_failure")

    def test_class_not_found(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("java.lang.NoClassDefFoundError: net/fabricmc/fabric/api/event/Event")

        self.assertEqual(diagnoses[0].kind, "class_not_found")

    def test_no_such_method_error(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("java.lang.NoSuchMethodError: net.minecraft.SomeClass.method()V")

        self.assertEqual(diagnoses[0].kind, "no_such_method_error")

    def test_client_only_mod_on_server(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("Attempted to load class net/minecraft/client/MinecraftClient for invalid dist DEDICATED_SERVER")

        self.assertEqual(diagnoses[0].kind, "client_only_mod_on_server")

    def test_server_only_mod_on_client(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("server-only mod attempted to load in client environment")

        self.assertEqual(diagnoses[0].kind, "server_only_mod_on_client")

    def test_unknown_failure_is_not_repairable(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("Game crashed after something unusual happened")

        self.assertEqual(diagnoses[0].kind, "unknown_launch_failure")
        self.assertFalse(diagnoses[0].suggested_repair_action_kinds)

    def test_crash_report_path_is_included_in_evidence(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure(
            "---- Minecraft Crash Report ----\nNoSuchMethodError: missing",
            evidence_paths=["C:/pack/crash-reports/crash-1.txt"],
        )

        self.assertEqual(diagnoses[0].kind, "crash_report")
        self.assertIn("C:/pack/crash-reports/crash-1.txt", diagnoses[0].evidence)
        self.assertEqual(diagnoses[1].kind, "no_such_method_error")

    def test_crash_report_diagnosis_is_ordered_before_specific_failure(self):
        from mythweaver.runtime.diagnosis import diagnose_runtime_failure

        diagnoses = diagnose_runtime_failure("---- Minecraft Crash Report ----\nMixin apply failed")

        self.assertEqual(diagnoses[0].kind, "crash_report")
        self.assertEqual(diagnoses[1].kind, "mixin_failure")


if __name__ == "__main__":
    unittest.main()
