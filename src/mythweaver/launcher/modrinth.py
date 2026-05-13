from __future__ import annotations

import os
from pathlib import Path

from mythweaver.schemas.contracts import (
    LaunchValidationReport,
    LauncherDetectionReport,
    LauncherInstanceReport,
    LauncherValidationReport,
)

from .validation import validate_launcher_instance


class ModrinthLauncherAdapter:
    launcher_name = "modrinth"

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = env or dict(os.environ)

    def detect_installation(self) -> LauncherDetectionReport:
        candidates = _modrinth_candidates(self.env)
        data_paths = [str(path) for path in candidates if path.exists()]
        executable_paths = [str(path) for path in _modrinth_executables(self.env) if path.exists()]
        status = "found" if data_paths or executable_paths else "not_found"
        notes = []
        if status == "not_found":
            notes.append("Modrinth App was not found in common APPDATA/LOCALAPPDATA locations.")
        return LauncherDetectionReport(
            status=status,
            launcher_name=self.launcher_name,
            data_paths=data_paths,
            executable_paths=executable_paths,
            notes=notes,
        )

    def create_or_import_instance(
        self,
        pack_artifact: Path,
        *,
        instance_name: str,
        minecraft_version: str,
        loader: str,
        loader_version: str | None,
        memory_mb: int,
        output_dir: Path,
    ) -> LauncherInstanceReport:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        instructions = output_dir / "launcher_import_instructions.md"
        instructions.write_text(
            "\n".join(
                [
                    "# Modrinth App import instructions",
                    "",
                    "MythWeaver did not use an undocumented Modrinth App import API.",
                    "1. Open Modrinth App.",
                    f"2. Import `{pack_artifact}`.",
                    f"3. Name the instance `{instance_name}`.",
                    f"4. Confirm Minecraft `{minecraft_version}` with `{loader}` loader"
                    + (f" `{loader_version}`." if loader_version else "."),
                    f"5. Set maximum memory to at least `{memory_mb}` MB.",
                    "6. Launch the instance, create a world, and wait for the smoke test window.",
                    "7. Run MythWeaver `setup-launcher --validate-only --instance-path <path>` after import.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return LauncherInstanceReport(
            status="manual_required",
            launcher_name=self.launcher_name,
            instance_name=instance_name,
            pack_artifact_path=str(pack_artifact),
            minecraft_version=minecraft_version,
            loader=loader,
            loader_version=loader_version,
            memory_mb=memory_mb,
            notes=[f"Wrote exact import/configuration instructions to {instructions}."],
        )

    def validate_instance(
        self,
        instance_path: Path,
        *,
        expected_minecraft_version: str,
        expected_loader: str,
        expected_loader_version: str | None,
        expected_memory_mb: int | None,
    ) -> LauncherValidationReport:
        return validate_launcher_instance(
            instance_path,
            launcher_name=self.launcher_name,
            expected_minecraft_version=expected_minecraft_version,
            expected_loader=expected_loader,
            expected_loader_version=expected_loader_version,
            expected_memory_mb=expected_memory_mb,
        )

    def launch_instance(
        self,
        instance_path: Path,
        *,
        wait_seconds: int,
        output_dir: Path,
        inject_smoke_test: bool = False,
        smoke_test_mod_injected: bool = False,
        validation_world: bool = False,
        keep_validation_world: bool = False,
    ) -> LaunchValidationReport:
        return LaunchValidationReport(
            status="manual_required",
            stage="not_started",
            summary=(
                "Modrinth App launch automation is not available through a stable documented local API. "
                f"Launch the instance, create a world, wait {wait_seconds} seconds, and provide logs/crash reports."
            ),
            output_dir=str(output_dir),
        )


def _modrinth_candidates(env: dict[str, str]) -> list[Path]:
    roots = [env.get("APPDATA"), env.get("LOCALAPPDATA"), env.get("USERPROFILE")]
    candidates: list[Path] = []
    for root in roots:
        if root:
            base = Path(root)
            candidates.extend([base / "ModrinthApp", base / "com.modrinth.theseus", base / ".modrinth"])
    return candidates


def _modrinth_executables(env: dict[str, str]) -> list[Path]:
    roots = [env.get("LOCALAPPDATA"), env.get("ProgramFiles"), env.get("ProgramFiles(x86)")]
    candidates: list[Path] = []
    for root in roots:
        if root:
            base = Path(root)
            candidates.extend([base / "Modrinth App" / "Modrinth App.exe", base / "Modrinth" / "Modrinth App.exe"])
    return candidates
