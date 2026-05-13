from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Callable, Literal, cast

from mythweaver.catalog.loaders import curseforge_loader_name, normalize_loader
from mythweaver.catalog.content_kinds import (
    content_kind_from_curseforge_class_id,
    default_placement_for_kind,
)
from mythweaver.schemas.contracts import SourceDependencyRecord, SourceFileCandidate, SourceSearchResult

_ENV_API_KEY = object()


class CurseForgeSourceProvider:
    source_name = "curseforge"
    trust_tier = "official_api"

    def __init__(
        self,
        api_key: str | None | object = _ENV_API_KEY,
        *,
        request_json: Callable[[str, dict[str, Any] | None], dict[str, Any]] | None = None,
    ) -> None:
        self.api_key: str | None = os.getenv("CURSEFORGE_API_KEY") if api_key is _ENV_API_KEY else cast(str | None, api_key)
        self._request_json = request_json
        self.base_url = "https://api.curseforge.com"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, *, minecraft_version: str, loader: str, limit: int = 20) -> SourceSearchResult:
        if not self.is_configured():
            return SourceSearchResult(query=query, source=self.source_name, warnings=["CURSEFORGE_API_KEY is not configured; CurseForge search skipped."])
        try:
            data = self._get_json("/v1/mods/search", {"gameId": 432, "searchFilter": query, "pageSize": limit})
        except (OSError, urllib.error.URLError) as exc:
            return SourceSearchResult(
                query=query,
                source=self.source_name,
                warnings=[f"CurseForge search skipped because the official API was unavailable: {exc}"],
            )
        candidates = []
        for item in data.get("data", [])[:limit]:
            candidate = await self.resolve_file(str(item.get("id") or item.get("slug")), minecraft_version=minecraft_version, loader=loader)
            if candidate:
                candidates.append(candidate)
        return SourceSearchResult(query=query, source=self.source_name, candidates=candidates)

    async def inspect(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        return await self.resolve_file(project_ref, minecraft_version=minecraft_version, loader=loader)

    async def pick_mod_and_file(
        self,
        project_ref: str,
        *,
        minecraft_version: str,
        loader: str,
        require_loader_match: bool = True,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Return (mod_json, file_json) for the best matching file, or None if none."""
        if not self.is_configured():
            return None
        mod = self._lookup_mod(project_ref)
        mod_id = str(mod.get("id") or project_ref)
        files = self._get_json(f"/v1/mods/{mod_id}/files", {"gameVersion": minecraft_version}).get("data", [])
        selected = _select_compatible_file(
            files,
            minecraft_version=minecraft_version,
            loader=loader,
            require_loader_match=require_loader_match,
        )
        if not selected:
            return None
        return mod, selected

    async def resolve_file(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        if not self.is_configured():
            return None
        mod = self._lookup_mod(project_ref)
        mod_id = str(mod.get("id") or project_ref)
        loader_name = curseforge_loader_name(loader)
        files = self._get_json(f"/v1/mods/{mod_id}/files", {"gameVersion": minecraft_version}).get("data", [])
        selected = _select_compatible_file(files, minecraft_version=minecraft_version, loader=loader, require_loader_match=True)
        if not selected:
            return SourceFileCandidate(
                source="curseforge",
                project_id=mod_id,
                slug=mod.get("slug"),
                name=mod.get("name") or project_ref,
                acquisition_status="unsupported",
                warnings=["No CurseForge file matched the requested Minecraft version and loader."],
            )
        game_versions = selected.get("gameVersions", [])
        loader_matches = loader_name is not None and _file_loader_matches(selected, loader)
        mc_matches = minecraft_version in game_versions
        hashes = _curseforge_hashes(selected.get("hashes", []))
        raw_download_url = selected.get("downloadUrl")
        download_url = raw_download_url if isinstance(raw_download_url, str) else None
        manifest_eligible = loader_matches and mc_matches and selected.get("id") is not None and mod_id
        status = (
            "verified_auto"
            if manifest_eligible and download_url and hashes
            else ("verified_manual_required" if manifest_eligible else "unsupported")
        )
        warnings = []
        if not loader_matches:
            warnings.append("CurseForge file does not advertise the requested loader.")
        if not mc_matches:
            warnings.append("CurseForge file does not advertise the requested Minecraft version.")
        if not download_url:
            warnings.append("CurseForge did not provide a direct official download URL; manual acquisition may be required.")
        if not hashes:
            warnings.append("CurseForge file did not include a supported hash.")
        dependency_records = [
            SourceDependencyRecord(
                source="curseforge",
                project_id=str(dep.get("modId")),
                dependency_type=_curseforge_dependency_type(dep.get("relationType")),
            )
            for dep in selected.get("dependencies", [])
            if dep.get("modId")
        ]
        class_id = mod.get("classId")
        inferred_kind = content_kind_from_curseforge_class_id(int(class_id)) if class_id is not None else None
        content_kind = inferred_kind or "mod"
        placement = default_placement_for_kind(content_kind)
        warnings = list(warnings)
        if inferred_kind is None and class_id is not None:
            warnings.append(f"CurseForge classId {class_id} has no MythWeaver content-kind mapping; defaulting to mod.")
        return SourceFileCandidate(
            source="curseforge",
            project_id=mod_id,
            file_id=str(selected.get("id")) if selected.get("id") is not None else None,
            slug=mod.get("slug"),
            name=selected.get("displayName") or mod.get("name") or project_ref,
            version_number=selected.get("displayName"),
            minecraft_versions=[item for item in game_versions if str(item)[0].isdigit()],
            loaders=_candidate_loaders(selected, loader),
            file_name=selected.get("fileName"),
            download_url=download_url,
            page_url=(mod.get("links") or {}).get("websiteUrl"),
            hashes=hashes,
            file_size_bytes=selected.get("fileLength"),
            dependencies=[dep.project_id for dep in dependency_records if dep.project_id],
            dependency_records=dependency_records,
            distribution_allowed="unknown",
            metadata_confidence="high" if status == "verified_auto" else "medium",
            acquisition_status=cast(
                Literal[
                    "verified_auto",
                    "verified_manual_required",
                    "metadata_incomplete",
                    "download_blocked",
                    "license_blocked",
                    "unsafe_source",
                    "unsupported",
                ],
                status,
            ),
            warnings=warnings,
            content_kind=content_kind,
            content_placement=placement,
        )

    def _lookup_mod(self, project_ref: str) -> dict[str, Any]:
        if project_ref.isdigit():
            return cast(dict[str, Any], self._get_json(f"/v1/mods/{project_ref}", None).get("data", {"id": int(project_ref), "name": project_ref}))
        data = self._get_json("/v1/mods/search", {"gameId": 432, "slug": project_ref, "searchFilter": project_ref, "pageSize": 1})
        items = data.get("data", [])
        return cast(dict[str, Any], items[0]) if items else {"id": project_ref, "slug": project_ref, "name": project_ref}

    def _get_json(self, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        if self._request_json:
            return self._request_json(path, params)
        encoded = urllib.parse.urlencode(params or {})
        request = urllib.request.Request(
            f"{self.base_url}{path}" + (f"?{encoded}" if encoded else ""),
            headers={"x-api-key": self.api_key or "", "User-Agent": "MythWeaver"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            import json

            return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))


def _curseforge_hashes(items: list[dict[str, Any]]) -> dict[str, str]:
    output: dict[str, str] = {}
    for item in items:
        algo = item.get("algo")
        if algo == 1:
            output["sha1"] = str(item.get("value", ""))
        elif algo == 2:
            output["md5"] = str(item.get("value", ""))
    return {key: value for key, value in output.items() if value}


def _select_compatible_file(
    files: list[dict[str, Any]],
    *,
    minecraft_version: str,
    loader: str,
    require_loader_match: bool = True,
) -> dict[str, Any] | None:
    compatible = [
        item
        for item in files
        if _file_matches_target(item, minecraft_version=minecraft_version, loader=loader, require_loader_match=require_loader_match)
    ]
    if not compatible:
        return None
    return sorted(compatible, key=_file_rank, reverse=True)[0]


def _file_matches_target(item: dict[str, Any], *, minecraft_version: str, loader: str, require_loader_match: bool = True) -> bool:
    game_versions = [str(value) for value in item.get("gameVersions", [])]
    if minecraft_version != "auto" and minecraft_version not in game_versions:
        return False
    if not require_loader_match:
        return True
    return _file_loader_matches(item, loader)


def _file_loader_matches(item: dict[str, Any], loader: str) -> bool:
    loader_name = curseforge_loader_name(loader)
    if not loader_name:
        return False
    game_versions = [str(value) for value in item.get("gameVersions", [])]
    if any(value.lower() == loader_name.lower() for value in game_versions):
        return True
    return _mod_loader_type_matches(item.get("modLoaderType"), normalize_loader(loader))


def _candidate_loaders(item: dict[str, Any], requested_loader: str) -> list[str]:
    loaders = [
        normalized
        for value in item.get("gameVersions", [])
        for text in [str(value)]
        for normalized in [normalize_loader(text)]
        if normalized not in {"unknown", "auto", "any"} and text and not text[0].isdigit()
    ]
    if not loaders and _file_loader_matches(item, requested_loader):
        loaders.append(normalize_loader(requested_loader))
    return list(dict.fromkeys(loaders))


def _file_rank(item: dict[str, Any]) -> tuple[int, datetime, int]:
    release_type = item.get("releaseType")
    release_rank = {1: 3, 2: 2, 3: 1}.get(cast(int, release_type), 0)
    return release_rank, _parse_date(item.get("fileDate")), int(item.get("id") or 0)


def _parse_date(value: Any) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.min


def _mod_loader_type_matches(value: Any, loader: str) -> bool:
    # CurseForge's official API primarily exposes loader names through gameVersions.
    # These numeric values are accepted as a fallback for mocked or partial metadata.
    mapping = {
        1: "forge",
        4: "fabric",
        5: "quilt",
        6: "neoforge",
    }
    return mapping.get(cast(int, value)) == loader


def _curseforge_dependency_type(value: Any) -> Literal["required", "optional", "incompatible", "embedded"]:
    if value == 2:
        return "optional"
    if value == 3:
        return "required"
    if value == 4:
        return "incompatible"
    if value == 5:
        return "embedded"
    return "required"
