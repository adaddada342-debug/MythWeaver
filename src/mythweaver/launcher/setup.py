from __future__ import annotations

from pathlib import Path

from mythweaver.launcher.detection import detect_launcher
from mythweaver.launcher.prism import resolve_registered_prism_instance
from mythweaver.schemas.contracts import LauncherInstanceReport, LauncherValidationReport


def setup_launcher_instance(
    pack_artifact: Path,
    *,
    launcher: str,
    instance_name: str,
    minecraft_version: str,
    loader: str,
    loader_version: str | None,
    memory_mb: int,
    output_dir: Path,
    validate_only: bool = False,
    instance_path: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[LauncherInstanceReport, LauncherValidationReport]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter = detect_launcher(launcher, env=env)
    if validate_only and instance_path:
        registration = resolve_registered_prism_instance(instance_path, env) if adapter.launcher_name == "prism" else None
        instance = LauncherInstanceReport(
            status="manual_required",
            launcher_name=adapter.launcher_name,
            instance_name=instance_name,
            instance_path=str(instance_path),
            generated_instance_path=str(instance_path),
            prism_registered_instance_path=str(registration[0]) if registration else None,
            prism_instance_id=registration[1] if registration else None,
            registered_with_prism=registration is not None,
            pack_artifact_path=str(pack_artifact),
            minecraft_version=minecraft_version,
            loader=loader,
            loader_version=loader_version,
            memory_mb=memory_mb,
            notes=[
                "Validated an existing launcher instance path.",
                "Instance is registered with Prism." if registration else "Instance is not registered with Prism; Prism launch automation requires registration.",
            ],
        )
    else:
        instance = adapter.create_or_import_instance(
            Path(pack_artifact),
            instance_name=instance_name,
            minecraft_version=minecraft_version,
            loader=loader,
            loader_version=loader_version,
            memory_mb=memory_mb,
            output_dir=output_dir,
        )
    validation_path = Path(instance_path or instance.instance_path) if (instance_path or instance.instance_path) else None
    if validation_path:
        validation = adapter.validate_instance(
            validation_path,
            expected_minecraft_version=minecraft_version,
            expected_loader=loader,
            expected_loader_version=loader_version,
            expected_memory_mb=memory_mb,
        )
    else:
        validation = LauncherValidationReport(
            status="manual_required",
            launcher_name=adapter.launcher_name,
            instance_path=None,
            minecraft_version=None,
            loader=None,
            loader_version=None,
            memory_mb=None,
            issues=[],
            summary="Launcher instance validation requires an imported instance path.",
        )
    return instance, validation


def write_launcher_reports(
    *,
    instance: LauncherInstanceReport,
    validation: LauncherValidationReport,
    output_dir: Path,
) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "launcher_instance_report.json").write_text(instance.model_dump_json(indent=2), encoding="utf-8")
    (output_dir / "launcher_validation_report.json").write_text(validation.model_dump_json(indent=2), encoding="utf-8")
