from __future__ import annotations

import json
import re
from pathlib import Path

from mythweaver.schemas.contracts import LauncherValidationIssue, LauncherValidationReport


def validate_launcher_instance(
    instance_path: Path,
    *,
    launcher_name: str,
    expected_minecraft_version: str,
    expected_loader: str,
    expected_loader_version: str | None,
    expected_memory_mb: int | None,
) -> LauncherValidationReport:
    instance_path = Path(instance_path)
    issues: list[LauncherValidationIssue] = []
    minecraft_version, loader, loader_version = _read_loader_metadata(instance_path)
    memory_mb = _read_memory_mb(instance_path)

    if not instance_path.exists():
        issues.append(
            LauncherValidationIssue(
                severity="critical",
                kind="missing_instance_metadata",
                title="Instance path does not exist",
                detail=str(instance_path),
                suggested_fix="Create/import the launcher instance before validation.",
            )
        )
    if minecraft_version is None and loader is None:
        issues.append(
            LauncherValidationIssue(
                severity="critical",
                kind="missing_instance_metadata",
                title="Instance metadata is missing",
                detail="No supported launcher metadata file was found.",
                suggested_fix="Import the .mrpack into the launcher or create a Prism instance with Fabric metadata.",
            )
        )
    if expected_minecraft_version and minecraft_version and minecraft_version != expected_minecraft_version:
        issues.append(
            LauncherValidationIssue(
                severity="critical",
                kind="wrong_minecraft_version",
                title="Minecraft version mismatch",
                detail=f"Expected {expected_minecraft_version}, found {minecraft_version}.",
                suggested_fix=f"Set the instance Minecraft version to {expected_minecraft_version}.",
            )
        )
    if expected_loader and not loader:
        issues.append(
            LauncherValidationIssue(
                severity="critical",
                kind="missing_loader",
                title="Expected mod loader is missing",
                detail=f"Expected {expected_loader}, but the instance metadata looks vanilla.",
                suggested_fix=f"Install/configure {expected_loader.title()} loader for this instance and reimport the .mrpack.",
            )
        )
        issues.append(
            LauncherValidationIssue(
                severity="critical",
                kind="vanilla_instance",
                title="Instance appears to be vanilla",
                detail="No Fabric/Forge loader component was found.",
                suggested_fix="Install/configure Fabric loader for this instance and reimport the .mrpack.",
            )
        )
    elif expected_loader and loader != expected_loader:
        issues.append(
            LauncherValidationIssue(
                severity="critical",
                kind="wrong_loader",
                title="Loader mismatch",
                detail=f"Expected {expected_loader}, found {loader}.",
                suggested_fix=f"Use a {expected_loader.title()} instance.",
            )
        )
    if expected_loader_version and loader_version and loader_version != expected_loader_version:
        issues.append(
            LauncherValidationIssue(
                severity="high",
                kind="wrong_loader_version",
                title="Loader version mismatch",
                detail=f"Expected {expected_loader_version}, found {loader_version}.",
                suggested_fix=f"Set loader version to {expected_loader_version}.",
            )
        )
    if expected_memory_mb is not None:
        if memory_mb is None:
            issues.append(
                LauncherValidationIssue(
                    severity="high",
                    kind="memory_not_set",
                    title="Maximum memory is not configured",
                    suggested_fix=f"Set maximum memory to at least {expected_memory_mb} MB.",
                )
            )
        elif memory_mb < expected_memory_mb:
            issues.append(
                LauncherValidationIssue(
                    severity="high",
                    kind="memory_too_low",
                    title="Maximum memory is too low",
                    detail=f"Expected at least {expected_memory_mb} MB, found {memory_mb} MB.",
                    suggested_fix=f"Set maximum memory to at least {expected_memory_mb} MB.",
                )
            )
    mods_folder = _mods_folder(instance_path)
    if not mods_folder.exists() or not any(mods_folder.iterdir()):
        issues.append(
            LauncherValidationIssue(
                severity="high",
                kind="missing_mods_folder",
                title="Mods folder is missing or empty",
                detail=str(mods_folder),
                suggested_fix="Import the .mrpack or copy generated mods into the instance mods folder.",
            )
        )

    failed = any(issue.severity in {"high", "critical"} for issue in issues)
    return LauncherValidationReport(
        status="failed" if failed else "passed",
        launcher_name=launcher_name,
        instance_path=str(instance_path),
        minecraft_version=minecraft_version,
        loader=loader,
        loader_version=loader_version,
        memory_mb=memory_mb,
        issues=issues,
        summary="Launcher instance validation failed." if failed else "Launcher instance validation passed.",
    )


def _read_loader_metadata(instance_path: Path) -> tuple[str | None, str | None, str | None]:
    mmc_pack = instance_path / "mmc-pack.json"
    if mmc_pack.is_file():
        data = json.loads(mmc_pack.read_text(encoding="utf-8"))
        minecraft = None
        loader = None
        loader_version = None
        for component in data.get("components", []):
            uid = str(component.get("uid", "")).lower()
            version = component.get("version")
            if uid == "net.minecraft":
                minecraft = version
            elif "fabric-loader" in uid:
                loader = "fabric"
                loader_version = version
            elif "forge" in uid:
                loader = "forge"
                loader_version = version
        return minecraft, loader, loader_version
    profile = instance_path / "profile.json"
    if profile.is_file():
        data = json.loads(profile.read_text(encoding="utf-8"))
        loader = str(data.get("loader") or data.get("modloader") or "").lower() or None
        return data.get("minecraft_version") or data.get("game_version"), loader, data.get("loader_version")
    return None, None, None


def _read_memory_mb(instance_path: Path) -> int | None:
    cfg = instance_path / "instance.cfg"
    if cfg.is_file():
        text = cfg.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"MaxMemAlloc\s*=\s*(\d+)", text)
        if match:
            return int(match.group(1))
        match = re.search(r"-Xmx(\d+)([mMgG])", text)
        if match:
            value = int(match.group(1))
            return value * 1024 if match.group(2).lower() == "g" else value
    return None


def _mods_folder(instance_path: Path) -> Path:
    minecraft_mods = instance_path / ".minecraft" / "mods"
    if minecraft_mods.exists():
        return minecraft_mods
    return instance_path / "mods"
