from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from mythweaver.schemas.contracts import SourceFileCandidate, SourceSearchResult


class LocalFileSourceProvider:
    source_name = "local"
    trust_tier = "semi_trusted"

    def is_configured(self) -> bool:
        return True

    async def search(self, query: str, *, minecraft_version: str, loader: str, limit: int = 20) -> SourceSearchResult:
        return SourceSearchResult(query=query, source=self.source_name, warnings=["Local provider requires explicit local:<path> refs."])

    async def inspect(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        path = _local_path(project_ref)
        if not path.is_file():
            return SourceFileCandidate(source="local", name=str(path), acquisition_status="unsupported", warnings=["Local file does not exist."])
        metadata = _read_jar_metadata(path)
        hashes = _hashes(path)
        loaders = metadata.get("loaders", [])
        versions = metadata.get("minecraft_versions", [])
        loader_ok = not loaders or loader in loaders
        version_ok = not versions or minecraft_version in versions or any(_constraint_matches(minecraft_version, item) for item in versions)
        verified = path.suffix.lower() == ".jar" and bool(hashes) and loader_ok and version_ok and bool(loaders or versions)
        warnings = []
        if not loader_ok:
            warnings.append("Local jar metadata does not match the requested loader.")
        if not version_ok:
            warnings.append("Local jar metadata does not match the requested Minecraft version.")
        if not metadata:
            warnings.append("Local jar metadata is incomplete.")
        return SourceFileCandidate(
            source="local",
            slug=metadata.get("id") or path.stem,
            name=metadata.get("name") or path.stem,
            version_number=metadata.get("version"),
            minecraft_versions=versions,
            loaders=loaders,
            file_name=path.name,
            download_url=str(path),
            hashes=hashes,
            file_size_bytes=path.stat().st_size,
            dependencies=metadata.get("dependencies", []),
            metadata_confidence="high" if metadata else "medium",
            acquisition_status="verified_auto" if verified else "metadata_incomplete",
            warnings=warnings,
        )

    async def resolve_file(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        return await self.inspect(project_ref, minecraft_version=minecraft_version, loader=loader)


def _local_path(project_ref: str) -> Path:
    return Path(project_ref.removeprefix("local:"))


def _hashes(path: Path) -> dict[str, str]:
    sha1 = hashlib.sha1()
    sha512 = hashlib.sha512()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha1.update(chunk)
            sha512.update(chunk)
    return {"sha1": sha1.hexdigest(), "sha512": sha512.hexdigest()}


def _read_jar_metadata(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            if "fabric.mod.json" in archive.namelist():
                data = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
                depends = data.get("depends", {})
                versions = []
                if isinstance(depends, dict) and depends.get("minecraft"):
                    versions.append(str(depends["minecraft"]).removeprefix("="))
                return {
                    "id": data.get("id"),
                    "name": data.get("name") or data.get("id"),
                    "version": data.get("version"),
                    "loaders": ["fabric"],
                    "minecraft_versions": versions,
                    "dependencies": [key for key in depends.keys() if key not in {"minecraft", "fabricloader"}] if isinstance(depends, dict) else [],
                }
            if "quilt.mod.json" in archive.namelist():
                data = json.loads(archive.read("quilt.mod.json").decode("utf-8"))
                return {"id": data.get("quilt_loader", {}).get("id"), "loaders": ["quilt"]}
            if "META-INF/mods.toml" in archive.namelist():
                return {"loaders": ["forge"]}
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError):
        return {}
    return {}


def _constraint_matches(target: str, constraint: str) -> bool:
    cleaned = constraint.strip().removeprefix("=").strip()
    return cleaned == target
