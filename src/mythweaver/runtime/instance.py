from __future__ import annotations

import os
import shutil
from pathlib import Path

from mythweaver.builders.paths import safe_file_name, safe_slug
from mythweaver.runtime.contracts import RuntimeLaunchRequest
from mythweaver.schemas.contracts import AgentSafeModel


class RuntimeInstance(AgentSafeModel):
    root: str
    minecraft_dir: str
    mods_dir: str
    config_dir: str
    logs_dir: str
    crash_reports_dir: str
    versions_dir: str
    libraries_dir: str
    assets_dir: str


def create_runtime_instance(request: RuntimeLaunchRequest, *, run_id: str) -> RuntimeInstance:
    output_root = Path(request.output_root or Path.cwd() / ".test-output")
    root = output_root / "runtime" / f"{safe_slug(request.instance_name, fallback='pack')}-{safe_slug(run_id, fallback='run')}"
    minecraft_dir = root / ".minecraft"
    mods_dir = minecraft_dir / "mods"
    config_target = minecraft_dir / "config"
    logs_dir = minecraft_dir / "logs"
    crash_reports_dir = minecraft_dir / "crash-reports"
    versions_dir = minecraft_dir / "versions"
    libraries_dir = minecraft_dir / "libraries"
    assets_dir = minecraft_dir / "assets"
    for directory in (mods_dir, config_target, logs_dir, crash_reports_dir, versions_dir, libraries_dir, assets_dir):
        directory.mkdir(parents=True, exist_ok=True)

    for mod_file in request.mod_files:
        source = Path(mod_file)
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, mods_dir / safe_file_name(source.name))
    if request.config_dir:
        config_source = Path(request.config_dir)
        if not config_source.is_dir():
            raise FileNotFoundError(config_source)
        for item in config_source.rglob("*"):
            if item.is_file():
                relative = item.relative_to(config_source)
                target = config_target / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
    return RuntimeInstance(
        root=os.fspath(root),
        minecraft_dir=os.fspath(minecraft_dir),
        mods_dir=os.fspath(mods_dir),
        config_dir=os.fspath(config_target),
        logs_dir=os.fspath(logs_dir),
        crash_reports_dir=os.fspath(crash_reports_dir),
        versions_dir=os.fspath(versions_dir),
        libraries_dir=os.fspath(libraries_dir),
        assets_dir=os.fspath(assets_dir),
    )
