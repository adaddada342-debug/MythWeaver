from __future__ import annotations

import json
import shutil
from pathlib import Path

from mythweaver.schemas.contracts import ValidationWorldReport

VALIDATION_WORLD_NAME = "MythWeaverRuntimeSmokeTest"


def create_validation_world(instance_path: Path, *, world_name: str = VALIDATION_WORLD_NAME) -> ValidationWorldReport:
    saves_path = Path(instance_path) / ".minecraft" / "saves"
    world_path = saves_path / world_name
    try:
        saves_path.mkdir(parents=True, exist_ok=True)
        if world_path.exists():
            return ValidationWorldReport(
                status="already_present",
                world_name=world_name,
                saves_path=str(saves_path),
                world_path=str(world_path),
                notes=["Validation world already exists; creation alone is not runtime proof."],
            )
        world_path.mkdir(parents=True, exist_ok=True)
        (world_path / "mythweaver_validation_world.json").write_text(
            json.dumps(
                {
                    "name": world_name,
                    "purpose": "MythWeaver runtime smoke-test placeholder world",
                    "runtime_proof": "Only smoke-test latest.log markers prove this world was entered.",
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return ValidationWorldReport(
            status="created",
            world_name=world_name,
            saves_path=str(saves_path),
            world_path=str(world_path),
            notes=["Created validation world placeholder; this does not prove it was loaded."],
        )
    except OSError as exc:
        return ValidationWorldReport(
            status="failed",
            world_name=world_name,
            saves_path=str(saves_path),
            world_path=str(world_path),
            errors=[str(exc)],
        )


def remove_validation_world(report: ValidationWorldReport) -> ValidationWorldReport:
    if not report.world_path:
        return report
    target = Path(report.world_path)
    try:
        if target.exists():
            shutil.rmtree(target)
        report.status = "removed"
        report.removed_after_validation = True
        report.notes.append("Removed validation-only world.")
    except OSError as exc:
        report.status = "failed"
        report.errors.append(str(exc))
    return report

