import unittest
from pathlib import Path
from unittest.mock import patch


class AutopilotDiagnosisPlanningTests(unittest.IsolatedAsyncioTestCase):
    async def test_autopilot_applies_only_safe_missing_dependency_diagnosis(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.loop import run_autopilot
        from mythweaver.runtime.contracts import RuntimeDiagnosis, RuntimeIssue, RuntimeLaunchReport, RuntimeProof
        from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport

        root = Path(".test-output") / "autopilot-diagnosis-safe"
        root.mkdir(parents=True, exist_ok=True)
        dep = root / "fabric-api.jar"
        dep.write_bytes(b"dep")
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(name="Diagnosis Pack", minecraft_version="1.20.1", loader="fabric", mods=[{"slug": "camera"}]).model_dump_json(),
            encoding="utf-8",
        )
        calls = 0

        async def fake_resolve(selected, **kwargs):
            import hashlib
            from mythweaver.schemas.contracts import SourceFileCandidate

            selected_files = []
            if any(entry.slug == "fabric-api" for entry in selected.mods):
                selected_files.append(
                    SourceFileCandidate(
                        source="local",
                        name="Fabric API",
                        file_name="fabric-api.jar",
                        download_url=str(dep),
                        hashes={"sha1": hashlib.sha1(b"dep").hexdigest()},
                        acquisition_status="verified_auto",
                    )
                )
            return SourceResolveReport(
                status="resolved",
                minecraft_version=kwargs["minecraft_version"],
                loader=kwargs["loader"],
                selected_files=selected_files,
                export_supported=True,
                dependency_closure_passed=True,
            )

        def fake_runtime(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                diagnosis = RuntimeDiagnosis(
                    kind="fabric_api_missing",
                    confidence="high",
                    summary="Fabric API is missing.",
                    evidence=["requires mod fabric-api"],
                    blocking=True,
                    affected_mod_ids=["fabric-api"],
                    suggested_repair_action_kinds=["add_mod"],
                )
                return RuntimeLaunchReport(
                    status="failed",
                    stage="classify",
                    instance_path=None,
                    minecraft_version=request.minecraft_version,
                    loader=request.loader,
                    loader_version=None,
                    java_path=None,
                    command_preview=[],
                    exit_code=1,
                    success_signal=None,
                    issues=[RuntimeIssue(kind="missing_dependency", severity="fatal", confidence=0.9, message="Missing fabric-api", evidence=[], missing_mods=["fabric-api"])],
                    recommended_next_actions=[],
                    logs_scanned=[],
                    warnings=[],
                    diagnoses=[diagnosis],
                )
            return RuntimeLaunchReport(
                status="passed",
                stage="monitor",
                instance_path=str(root / "runtime"),
                minecraft_version=request.minecraft_version,
                loader=request.loader,
                loader_version=None,
                java_path=None,
                command_preview=[],
                exit_code=0,
                success_signal="MythWeaver smoke-test proof: stable_60",
                issues=[],
                recommended_next_actions=[],
                logs_scanned=[],
                warnings=[],
                proof=RuntimeProof(
                    proof_level="stable_60",
                    runtime_proof_observed=True,
                    smoke_test_mod_used=True,
                    smoke_test_markers_seen=["CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_60_SECONDS"],
                    required_markers_met=True,
                    stability_seconds_proven=60,
                ),
            )

        with (
            patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", fake_resolve),
            patch("mythweaver.autopilot.loop.run_runtime_validation", fake_runtime),
        ):
            report = await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    sources=["modrinth"],
                    minecraft_version="1.20.1",
                    loader="fabric",
                    output_root=str(root),
                    max_attempts=2,
                )
            )

        self.assertEqual(report.status, "verified_playable")
        self.assertEqual(report.attempts[0].diagnoses[0].kind, "fabric_api_missing")
        self.assertEqual(report.attempts[0].actions_applied[0].status, "applied")

    async def test_autopilot_blocks_unsupported_diagnosis_without_repair(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.loop import run_autopilot
        from mythweaver.runtime.contracts import RuntimeDiagnosis, RuntimeLaunchReport
        from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport

        root = Path(".test-output") / "autopilot-diagnosis-blocked"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(name="Blocked Pack", minecraft_version="1.20.1", loader="fabric", mods=[{"slug": "forge-mod"}]).model_dump_json(),
            encoding="utf-8",
        )

        async def fake_resolve(selected, **kwargs):
            return SourceResolveReport(
                status="resolved",
                minecraft_version=kwargs["minecraft_version"],
                loader=kwargs["loader"],
                selected_files=[],
                export_supported=True,
                dependency_closure_passed=True,
            )

        def fake_runtime(request):
            diagnosis = RuntimeDiagnosis(
                kind="wrong_loader",
                confidence="high",
                summary="A Forge mod was loaded in Fabric.",
                evidence=["requires forge"],
                blocking=True,
                suggested_repair_action_kinds=["manual_review"],
            )
            return RuntimeLaunchReport(
                status="failed",
                stage="classify",
                instance_path=None,
                minecraft_version=request.minecraft_version,
                loader=request.loader,
                loader_version=None,
                java_path=None,
                command_preview=[],
                exit_code=1,
                success_signal=None,
                issues=[],
                recommended_next_actions=[],
                logs_scanned=[],
                warnings=[],
                diagnoses=[diagnosis],
            )

        with (
            patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", fake_resolve),
            patch("mythweaver.autopilot.loop.run_runtime_validation", fake_runtime),
        ):
            report = await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    sources=["modrinth"],
                    minecraft_version="1.20.1",
                    loader="fabric",
                    output_root=str(root),
                    max_attempts=2,
                )
            )

        self.assertEqual(report.status, "blocked")
        self.assertEqual(report.attempts[0].diagnoses[0].kind, "wrong_loader")
        self.assertFalse(report.attempts[0].actions_applied)


if __name__ == "__main__":
    unittest.main()
