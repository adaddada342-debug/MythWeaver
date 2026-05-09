from __future__ import annotations

from pathlib import Path
from typing import Protocol

from mythweaver.schemas.contracts import (
    LaunchValidationReport,
    LauncherDetectionReport,
    LauncherInstanceReport,
    LauncherValidationReport,
)


class LauncherAdapter(Protocol):
    launcher_name: str

    def detect_installation(self) -> LauncherDetectionReport:
        ...

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
        ...

    def validate_instance(
        self,
        instance_path: Path,
        *,
        expected_minecraft_version: str,
        expected_loader: str,
        expected_loader_version: str | None,
        expected_memory_mb: int | None,
    ) -> LauncherValidationReport:
        ...

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
        ...
