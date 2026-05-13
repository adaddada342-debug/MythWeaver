from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

from mythweaver.builders.paths import safe_relative_path
from mythweaver.catalog.loaders import curseforge_loader_name, normalize_loader
from mythweaver.schemas.contracts import BuildArtifact, SourceFileCandidate, SourceResolveReport


def build_curseforge_manifest(
    pack_or_source_report: SourceResolveReport,
    output_path: Path,
    overrides: dict[str, Path] | None = None,
    *,
    name: str | None = None,
    version: str = "1.0.0",
    author: str | None = None,
    loader_version: str | None = None,
) -> BuildArtifact:
    report = pack_or_source_report
    loader_id = _loader_id(report.loader, loader_version)
    files = [_manifest_file_entry(candidate) for candidate in report.manifest_files]
    if not files:
        raise ValueError("CurseForge manifest export requires at least one manifest file.")

    manifest = {
        "minecraft": {
            "version": report.minecraft_version,
            "modLoaders": [{"id": loader_id, "primary": True}],
        },
        "manifestType": "minecraftModpack",
        "manifestVersion": 1,
        "name": name or "MythWeaver Pack",
        "version": version,
        "author": author or "MythWeaver",
        "files": files,
        "overrides": "overrides",
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))
        for target, source in (overrides or {}).items():
            safe_target = safe_relative_path(target)
            source_path = Path(source)
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            archive.write(source_path, f"overrides/{safe_target.as_posix()}")

    return BuildArtifact(
        kind="curseforge-manifest",
        path=os.fspath(output_path),
        metadata={"files": len(files), "loader": loader_id},
    )


def _loader_id(loader: str, loader_version: str | None) -> str:
    name = curseforge_loader_name(loader)
    if name is None:
        raise ValueError(f"unsupported CurseForge manifest loader: {loader}")
    normalized = normalize_loader(loader)
    if normalized == "neoforge":
        base = "neoforge"
    else:
        base = name.lower().replace(" ", "")
    if not loader_version:
        return base
    return f"{base}-{loader_version}"


def _manifest_file_entry(candidate: SourceFileCandidate) -> dict[str, object]:
    if candidate.source != "curseforge":
        raise ValueError("CurseForge manifest export refuses non-CurseForge files.")
    if candidate.acquisition_status not in {"verified_auto", "verified_manual_required"}:
        raise ValueError(f"CurseForge file {candidate.name} is not manifest-eligible: {candidate.acquisition_status}.")
    if not candidate.project_id:
        raise ValueError(f"CurseForge file {candidate.name} is missing projectID.")
    if not candidate.file_id:
        raise ValueError(f"CurseForge file {candidate.name} is missing fileID.")
    try:
        project_id = int(candidate.project_id)
        file_id = int(candidate.file_id)
    except ValueError as exc:
        raise ValueError("CurseForge projectID and fileID must be numeric.") from exc
    return {"projectID": project_id, "fileID": file_id, "required": True}
