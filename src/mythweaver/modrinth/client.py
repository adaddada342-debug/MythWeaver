from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from mythweaver.db.cache import SQLiteCache
from mythweaver.modrinth.facets import build_search_facets
from mythweaver.catalog.content_kinds import content_kind_from_modrinth_project_type
from mythweaver.schemas.contracts import (
    CandidateMod,
    DependencyRecord,
    ModFile,
    ModVersion,
    SearchPlan,
)


@dataclass(frozen=True)
class ModrinthResponse:
    status: int
    data: Any
    headers: dict[str, str]


class ModrinthClient:
    """Async Modrinth API v2 client using deterministic caching and stdlib HTTP."""

    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        cache: SQLiteCache | None = None,
        cache_ttl_seconds: int = 3600,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_retries = max_retries

    async def search_projects(self, plan: SearchPlan) -> dict[str, Any]:
        params = {
            "query": plan.query,
            "facets": build_search_facets(plan),
            "index": plan.index,
            "offset": str(plan.offset),
            "limit": str(plan.limit),
        }
        return await self.get_json("/search", params=params)

    async def list_project_versions(
        self,
        project_id_or_slug: str,
        *,
        loader: str,
        minecraft_version: str,
        include_changelog: bool = False,
        use_loader_filter: bool = True,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "include_changelog": "true" if include_changelog else "false",
        }
        if use_loader_filter:
            params["loaders"] = json.dumps([loader])
        if minecraft_version != "auto":
            params["game_versions"] = json.dumps([minecraft_version])
        versions = await self.get_json(f"/project/{project_id_or_slug}/version", params=params)
        if not isinstance(versions, list):
            raise ValueError("expected Modrinth versions response to be a list")
        return versions

    async def get_project(self, project_id_or_slug: str) -> dict[str, Any]:
        result = await self.get_json(f"/project/{project_id_or_slug}")
        if not isinstance(result, dict):
            raise ValueError("expected Modrinth project response to be an object")
        return result

    async def get_project_dependencies(self, project_id_or_slug: str) -> dict[str, Any]:
        result = await self.get_json(f"/project/{project_id_or_slug}/dependencies")
        if not isinstance(result, dict):
            raise ValueError("expected Modrinth dependency response to be an object")
        return result

    async def get_game_versions(self) -> list[dict[str, Any]]:
        result = await self.get_json("/tag/game_version")
        if not isinstance(result, list):
            raise ValueError("expected Modrinth game versions response to be a list")
        return result

    async def get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        url = self._url(path, params)
        cache_key = f"modrinth:{url}"
        if self.cache:
            cached = self.cache.get_json(cache_key)
            if cached is not None:
                return cached
        response = await self._request_json(url)
        if self.cache:
            self.cache.set_json(cache_key, response.data, self.cache_ttl_seconds)
        return response.data

    def _url(self, path: str, params: dict[str, str] | None) -> str:
        encoded = urllib.parse.urlencode(params or {})
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}" + (f"?{encoded}" if encoded else "")

    async def _request_json(self, url: str) -> ModrinthResponse:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return await asyncio.to_thread(self._request_json_sync, url)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code == 429:
                    reset = exc.headers.get("X-Ratelimit-Reset")
                    delay = float(reset) if reset and reset.isdigit() else attempt
                    await asyncio.sleep(min(delay, 10.0))
                    continue
                if 500 <= exc.code < 600:
                    await asyncio.sleep(attempt)
                    continue
                raise
            except OSError as exc:
                last_error = exc
                await asyncio.sleep(attempt)
        if last_error:
            raise last_error
        raise RuntimeError("unreachable Modrinth request failure")

    def _request_json_sync(self, url: str) -> ModrinthResponse:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            headers = {key: value for key, value in response.headers.items()}
            remaining = headers.get("X-Ratelimit-Remaining")
            reset = headers.get("X-Ratelimit-Reset")
            if remaining == "0" and reset:
                time.sleep(min(float(reset), 10.0))
            return ModrinthResponse(response.status, json.loads(raw), headers)


def candidate_from_project_hit(hit: dict[str, Any], version: dict[str, Any]) -> CandidateMod:
    """Map Modrinth search + selected version data into MythWeaver contracts."""

    files = [
        ModFile(
            filename=file["filename"],
            url=file["url"],
            hashes=file["hashes"],
            size=file.get("size", file.get("fileSize", 0)),
            primary=file.get("primary", False),
            file_type=file.get("file_type"),
        )
        for file in version.get("files", [])
    ]
    dependencies = [
        DependencyRecord(
            version_id=dependency.get("version_id"),
            project_id=dependency.get("project_id"),
            file_name=dependency.get("file_name"),
            dependency_type=dependency.get("dependency_type", "required"),
        )
        for dependency in version.get("dependencies", [])
    ]
    selected_version = ModVersion(
        id=version["id"],
        project_id=version["project_id"],
        version_number=version.get("version_number", ""),
        game_versions=version.get("game_versions", []),
        loaders=version.get("loaders", []),
        version_type=version.get("version_type", "release"),
        status=version.get("status", "listed"),
        dependencies=dependencies,
        files=files,
        date_published=version.get("date_published"),
        downloads=version.get("downloads", 0),
    )
    project_id = hit.get("project_id") or hit.get("id") or selected_version.project_id
    kind, raw_pt = content_kind_from_modrinth_project_type(hit.get("project_type"))
    return CandidateMod(
        project_id=project_id,
        slug=hit.get("slug", project_id),
        title=hit.get("title", project_id),
        description=hit.get("description", ""),
        categories=hit.get("categories", []),
        client_side=hit.get("client_side", "unknown"),
        server_side=hit.get("server_side", "unknown"),
        downloads=hit.get("downloads", 0),
        follows=hit.get("follows", 0),
        updated=hit.get("date_modified") or hit.get("updated"),
        loaders=hit.get("loaders", selected_version.loaders),
        game_versions=hit.get("versions", selected_version.game_versions),
        selected_version=selected_version,
        dependency_count=len(dependencies),
        content_kind=kind,
        platform_project_type=raw_pt,
    )
