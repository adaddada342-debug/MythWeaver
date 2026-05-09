from __future__ import annotations

from mythweaver.modrinth.client import candidate_from_project_hit
from mythweaver.schemas.contracts import SearchPlan, SourceDependencyRecord, SourceFileCandidate, SourceSearchResult


class ModrinthSourceProvider:
    source_name = "modrinth"
    trust_tier = "official_api"

    def __init__(self, modrinth) -> None:
        self.modrinth = modrinth

    def is_configured(self) -> bool:
        return self.modrinth is not None

    async def search(self, query: str, *, minecraft_version: str, loader: str, limit: int = 20) -> SourceSearchResult:
        if not self.is_configured():
            return SourceSearchResult(query=query, source=self.source_name, warnings=["Modrinth client is not configured."])
        plan = SearchPlan(query=query, minecraft_version=minecraft_version, loader=loader, limit=limit)
        data = await self.modrinth.search_projects(plan)
        candidates = []
        for hit in data.get("hits", [])[:limit]:
            candidate = await self.resolve_file(hit.get("slug") or hit.get("project_id") or hit.get("id"), minecraft_version=minecraft_version, loader=loader)
            if candidate:
                candidates.append(candidate)
        return SourceSearchResult(query=query, source=self.source_name, candidates=candidates)

    async def inspect(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        return await self.resolve_file(project_ref, minecraft_version=minecraft_version, loader=loader)

    async def resolve_file(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        if not self.is_configured() or not project_ref:
            return None
        try:
            project = await self.modrinth.get_project(project_ref)
            versions = await self.modrinth.list_project_versions(project_ref, loader=loader, minecraft_version=minecraft_version)
        except Exception:
            return None
        if not versions:
            return SourceFileCandidate(
                source="modrinth",
                project_id=project.get("id") or project_ref,
                slug=project.get("slug") or project_ref,
                name=project.get("title") or project_ref,
                minecraft_versions=project.get("versions", []),
                loaders=project.get("loaders", []),
                page_url=f"https://modrinth.com/mod/{project.get('slug') or project_ref}",
                acquisition_status="unsupported",
                warnings=["No Modrinth file matched the requested loader/version."],
            )
        version = versions[0]
        mapped = candidate_from_project_hit(project, version)
        primary = mapped.primary_file()
        dependency_records = [
            SourceDependencyRecord(
                source="modrinth",
                project_id=dep.project_id,
                version_id=dep.version_id,
                file_name=dep.file_name,
                dependency_type=dep.dependency_type,
            )
            for dep in mapped.selected_version.dependencies
            if dep.project_id or dep.version_id or dep.file_name
        ]
        dependencies = [dep.project_id for dep in dependency_records if dep.project_id]
        verified = (
            loader in mapped.selected_version.loaders
            and (minecraft_version == "auto" or minecraft_version in mapped.selected_version.game_versions)
            and bool(primary.url)
            and bool(primary.hashes)
        )
        return SourceFileCandidate(
            source="modrinth",
            project_id=mapped.project_id,
            file_id=mapped.selected_version.id,
            slug=mapped.slug,
            name=mapped.title,
            version_number=mapped.selected_version.version_number,
            minecraft_versions=mapped.selected_version.game_versions,
            loaders=mapped.selected_version.loaders,
            file_name=primary.filename,
            download_url=primary.url,
            page_url=f"https://modrinth.com/mod/{mapped.slug}",
            hashes=primary.hashes,
            file_size_bytes=primary.size,
            dependencies=dependencies,
            dependency_records=dependency_records,
            side="unknown",
            license=project.get("license", {}).get("id") if isinstance(project.get("license"), dict) else project.get("license"),
            distribution_allowed="yes",
            metadata_confidence="high",
            acquisition_status="verified_auto" if verified else "metadata_incomplete",
            warnings=[] if verified else ["Modrinth metadata was incomplete for autonomous acquisition."],
        )
