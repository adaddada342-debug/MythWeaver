import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch


class AutopilotLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_autopilot_applies_missing_dependency_and_retries_to_verified_playable(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.loop import run_autopilot
        from mythweaver.runtime.contracts import RuntimeIssue, RuntimeLaunchReport, RuntimeProof
        from mythweaver.schemas.contracts import SelectedModList, SourceFileCandidate, SourceResolveReport

        root = Path(".test-output") / "autopilot-loop"
        root.mkdir(parents=True, exist_ok=True)
        mod = root / "mod.jar"
        dep = root / "fabric-api.jar"
        mod.write_bytes(b"mod")
        dep.write_bytes(b"dep")
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(name="Loop Pack", minecraft_version="1.20.1", loader="fabric", mods=[{"slug": "cameraoverhaul"}]).model_dump_json(),
            encoding="utf-8",
        )
        runtime_calls = []

        async def fake_resolve(selected, *, minecraft_version, loader, sources, target_export, autonomous, modrinth=None, curseforge_api_key=None, allow_manual_sources=False):
            files = [
                SourceFileCandidate(
                    source="local",
                    name="Camera",
                    file_name="mod.jar",
                    download_url=str(mod),
                    hashes={"sha1": hashlib.sha1(b"mod").hexdigest()},
                    acquisition_status="verified_auto",
                )
            ]
            if any(entry.slug == "fabric-api" for entry in selected.mods):
                files.append(
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
                minecraft_version=minecraft_version,
                loader=loader,
                selected_files=files,
                required_count=len(selected.mods),
                export_supported=True,
                dependency_closure_passed=True,
            )

        def fake_runtime(request):
            runtime_calls.append(list(request.mod_files))
            if len(runtime_calls) == 1:
                return RuntimeLaunchReport(
                    status="failed",
                    stage="classify",
                    instance_path=None,
                    minecraft_version=request.minecraft_version,
                    loader=request.loader,
                    loader_version=request.loader_version,
                    java_path=request.java_path,
                    command_preview=[],
                    exit_code=1,
                    success_signal=None,
                    issues=[RuntimeIssue(kind="missing_dependency", severity="fatal", confidence=0.9, message="Missing fabric-api", evidence=[], missing_mods=["fabric-api"])],
                    recommended_next_actions=[],
                    logs_scanned=[],
                    warnings=[],
                )
            return RuntimeLaunchReport(
                status="passed",
                stage="monitor",
                instance_path=str(root / "runtime-final"),
                minecraft_version=request.minecraft_version,
                loader=request.loader,
                loader_version=request.loader_version,
                java_path=request.java_path,
                command_preview=[],
                exit_code=0,
                success_signal="Sound engine started",
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
                    evidence_path=str(root / "runtime_evidence.txt"),
                ),
            )

        with (
            patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", fake_resolve),
            patch("mythweaver.autopilot.loop.run_runtime_validation", fake_runtime),
        ):
            report = await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    sources=["local"],
                    minecraft_version="1.20.1",
                    loader="fabric",
                    output_root=str(root),
                    max_attempts=3,
                )
            )

        self.assertEqual(report.status, "verified_playable")
        self.assertEqual(report.final_proof.proof_level, "stable_60")
        self.assertEqual(len(report.attempts), 2)
        self.assertEqual(report.attempts[0].actions_applied[0].status, "applied")
        self.assertNotIn("fabric-api", selected_path.read_text(encoding="utf-8"))

    async def test_autopilot_stops_when_same_issue_repeats(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.loop import run_autopilot
        from mythweaver.runtime.contracts import RuntimeIssue, RuntimeLaunchReport
        from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport

        root = Path(".test-output") / "autopilot-repeat"
        root.mkdir(parents=True, exist_ok=True)
        (root / "fabric-api.jar").write_bytes(b"dep")
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(name="Repeat Pack", minecraft_version="1.20.1", loader="fabric", mods=[{"slug": "a"}]).model_dump_json(),
            encoding="utf-8",
        )

        async def fake_resolve(selected, **kwargs):
            from mythweaver.schemas.contracts import SourceFileCandidate

            selected_files = []
            if any(entry.slug == "fabric-api" for entry in selected.mods):
                selected_files.append(
                    SourceFileCandidate(
                        source="local",
                        name="Fabric API",
                        file_name="fabric-api.jar",
                        download_url=str(root / "fabric-api.jar"),
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
            )

        with (
            patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", fake_resolve),
            patch("mythweaver.autopilot.loop.run_runtime_validation", fake_runtime),
        ):
            report = await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    sources=["local"],
                    minecraft_version="1.20.1",
                    loader="fabric",
                    output_root=str(root),
                    max_attempts=5,
                )
            )

        self.assertEqual(report.status, "blocked")
        self.assertIn("repeated", report.summary.lower())

    async def test_autopilot_stops_when_max_attempts_reached(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.loop import run_autopilot
        from mythweaver.runtime.contracts import RuntimeIssue, RuntimeLaunchReport
        from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport

        root = Path(".test-output") / "autopilot-max"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(name="Max Pack", minecraft_version="1.20.1", loader="fabric", mods=[{"slug": "a"}]).model_dump_json(),
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
            )

        with (
            patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", fake_resolve),
            patch("mythweaver.autopilot.loop.run_runtime_validation", fake_runtime),
        ):
            report = await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    sources=["local"],
                    minecraft_version="1.20.1",
                    loader="fabric",
                    output_root=str(root),
                    max_attempts=1,
                )
            )

        self.assertEqual(report.status, "max_attempts_reached")
        self.assertEqual(len(report.attempts), 1)

    async def test_autopilot_does_not_verify_weak_runtime_proof(self):
        from mythweaver.autopilot.contracts import AutopilotRequest
        from mythweaver.autopilot.loop import run_autopilot
        from mythweaver.runtime.contracts import RuntimeLaunchReport, RuntimeProof
        from mythweaver.schemas.contracts import SelectedModList, SourceResolveReport

        root = Path(".test-output") / "autopilot-weak-proof"
        root.mkdir(parents=True, exist_ok=True)
        selected_path = root / "selected_mods.json"
        selected_path.write_text(
            SelectedModList(name="Weak Pack", minecraft_version="1.20.1", loader="fabric", mods=[]).model_dump_json(),
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
                success_signal="Weak runtime signal: Sound engine started",
                issues=[],
                recommended_next_actions=[],
                logs_scanned=[],
                warnings=[],
                proof=RuntimeProof(
                    proof_level="client_initialized",
                    runtime_proof_observed=False,
                    smoke_test_mod_used=False,
                    smoke_test_markers_seen=["CLIENT_READY"],
                    required_markers_met=False,
                    stability_seconds_proven=0,
                ),
            )

        with (
            patch("mythweaver.autopilot.loop.resolve_sources_for_selected_mods", fake_resolve),
            patch("mythweaver.autopilot.loop.run_runtime_validation", fake_runtime),
        ):
            report = await run_autopilot(
                AutopilotRequest(
                    selected_mods_path=str(selected_path),
                    sources=["local"],
                    minecraft_version="1.20.1",
                    loader="fabric",
                    output_root=str(root),
                    max_attempts=1,
                )
            )

        self.assertNotEqual(report.status, "verified_playable")
        self.assertEqual(report.status, "max_attempts_reached")
        self.assertEqual(report.attempts[0].proof.proof_level, "client_initialized")
        self.assertNotIn("fabric-api", selected_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
