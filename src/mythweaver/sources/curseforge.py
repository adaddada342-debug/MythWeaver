from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

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
        self.api_key = os.getenv("CURSEFORGE_API_KEY") if api_key is _ENV_API_KEY else api_key
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

    async def resolve_file(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        if not self.is_configured():
            return None
        mod = self._lookup_mod(project_ref)
        mod_id = str(mod.get("id") or project_ref)
        files = self._get_json(f"/v1/mods/{mod_id}/files", {"gameVersion": minecraft_version}).get("data", [])
        selected = files[0] if files else None
        if not selected:
            return SourceFileCandidate(source="curseforge", project_id=mod_id, slug=mod.get("slug"), name=mod.get("name") or project_ref, acquisition_status="unsupported", warnings=["No CurseForge file matched the requested Minecraft version."])
        game_versions = selected.get("gameVersions", [])
        loader_matches = any(str(item).lower() == loader.lower() for item in game_versions)
        mc_matches = minecraft_version in game_versions
        hashes = _curseforge_hashes(selected.get("hashes", []))
        download_url = selected.get("downloadUrl")
        status = "verified_auto" if loader_matches and mc_matches and download_url and hashes else ("unsupported" if not (loader_matches and mc_matches) else "metadata_incomplete")
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
        return SourceFileCandidate(
            source="curseforge",
            project_id=mod_id,
            file_id=str(selected.get("id")) if selected.get("id") is not None else None,
            slug=mod.get("slug"),
            name=selected.get("displayName") or mod.get("name") or project_ref,
            version_number=selected.get("displayName"),
            minecraft_versions=[item for item in game_versions if str(item)[0].isdigit()],
            loaders=[item.lower() for item in game_versions if str(item).lower() in {"fabric", "forge", "quilt", "neoforge"}],
            file_name=selected.get("fileName"),
            download_url=download_url,
            page_url=(mod.get("links") or {}).get("websiteUrl"),
            hashes=hashes,
            file_size_bytes=selected.get("fileLength"),
            dependencies=[dep.project_id for dep in dependency_records if dep.project_id],
            dependency_records=dependency_records,
            distribution_allowed="unknown",
            metadata_confidence="high" if status == "verified_auto" else "medium",
            acquisition_status=status,
            warnings=warnings,
        )

    def _lookup_mod(self, project_ref: str) -> dict[str, Any]:
        if project_ref.isdigit():
            return self._get_json(f"/v1/mods/{project_ref}", None).get("data", {"id": int(project_ref), "name": project_ref})
        data = self._get_json("/v1/mods/search", {"gameId": 432, "slug": project_ref, "searchFilter": project_ref, "pageSize": 1})
        items = data.get("data", [])
        return items[0] if items else {"id": project_ref, "slug": project_ref, "name": project_ref}

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

            return json.loads(response.read().decode("utf-8"))


def _curseforge_hashes(items: list[dict[str, Any]]) -> dict[str, str]:
    output: dict[str, str] = {}
    for item in items:
        algo = item.get("algo")
        if algo == 1:
            output["sha1"] = item.get("value", "")
        elif algo == 2:
            output["md5"] = item.get("value", "")
    return {key: value for key, value in output.items() if value}


def _curseforge_dependency_type(value: Any) -> str:
    if value == 2:
        return "optional"
    if value == 3:
        return "required"
    if value == 4:
        return "incompatible"
    if value == 5:
        return "embedded"
    return "required"
