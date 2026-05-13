from __future__ import annotations

from typing import Any, cast

from mythweaver.catalog.content_kinds import (
    content_kind_from_modrinth_project_type,
    default_placement_for_kind,
    modrinth_version_uses_loader_filter,
)
from mythweaver.catalog.modrinth_datapack_edge import (
    PLATFORM_MOD_DATAPACK_FILE_WARNING,
    first_installable_modrinth_version_dict,
    modrinth_mod_project_datapack_edge_applies,
)
from mythweaver.modrinth.client import candidate_from_project_hit
from mythweaver.catalog.loaders import modrinth_loader_category, normalize_loader
from mythweaver.schemas.contracts import RequestedLoader, SearchPlan, SourceDependencyRecord, SourceFileCandidate, SourceSearchResult


def _modrinth_web_segment(kind: str) -> str:
    if kind == "shaderpack":
        return "shader"
    if kind == "modpack":
        return "modpack"
    if kind == "resourcepack":
        return "resourcepack"
    if kind == "datapack":
        return "datapack"
    return "mod"


class ModrinthSourceProvider:
    source_name = "modrinth"
    trust_tier = "official_api"

    def __init__(self, modrinth: Any) -> None:
        self.modrinth = modrinth

    def is_configured(self) -> bool:
        return self.modrinth is not None

    async def search(self, query: str, *, minecraft_version: str, loader: str, limit: int = 20) -> SourceSearchResult:
        if not self.is_configured():
            return SourceSearchResult(query=query, source=self.source_name, warnings=["Modrinth client is not configured."])
        plan = SearchPlan(query=query, minecraft_version=minecraft_version, loader=cast(RequestedLoader, normalize_loader(loader)), limit=limit)
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
            content_kind, _ = content_kind_from_modrinth_project_type(project.get("project_type"))
            loader_category = modrinth_loader_category(loader) or normalize_loader(loader)
            versions = await self.modrinth.list_project_versions(
                project_ref,
                loader=loader_category,
                minecraft_version=minecraft_version,
                use_loader_filter=modrinth_version_uses_loader_filter(content_kind),
            )
            if (
                not versions
                and str(project.get("project_type", "")).strip().lower() == "mod"
                and content_kind == "mod"
            ):
                versions = await self.modrinth.list_project_versions(
                    project_ref,
                    loader=loader_category,
                    minecraft_version=minecraft_version,
                    use_loader_filter=False,
                )
        except Exception:
            return None
        if not versions:
            ck, _ = content_kind_from_modrinth_project_type(project.get("project_type"))
            slug = project.get("slug") or project_ref
            seg = _modrinth_web_segment(ck)
            return SourceFileCandidate(
                source="modrinth",
                project_id=project.get("id") or project_ref,
                slug=slug,
                name=project.get("title") or project_ref,
                minecraft_versions=project.get("versions", []),
                loaders=project.get("loaders", []),
                page_url=f"https://modrinth.com/{seg}/{slug}",
                acquisition_status="unsupported",
                warnings=["No Modrinth file matched the requested loader/version."],
                content_kind=ck,
                content_placement=default_placement_for_kind(ck),
            )
        require_lm = modrinth_version_uses_loader_filter(content_kind)
        version = first_installable_modrinth_version_dict(
            project,
            versions,
            loader=loader,
            minecraft_version=minecraft_version,
            require_loader_match=require_lm,
        )
        if version is None:
            ck, _ = content_kind_from_modrinth_project_type(project.get("project_type"))
            slug = project.get("slug") or project_ref
            seg = _modrinth_web_segment(ck)
            return SourceFileCandidate(
                source="modrinth",
                project_id=project.get("id") or project_ref,
                slug=slug,
                name=project.get("title") or project_ref,
                minecraft_versions=project.get("versions", []),
                loaders=project.get("loaders", []),
                page_url=f"https://modrinth.com/{seg}/{slug}",
                acquisition_status="unsupported",
                warnings=["No Modrinth file matched the requested loader/version."],
                content_kind=ck,
                content_placement=default_placement_for_kind(ck),
            )
        mapped = candidate_from_project_hit(project, version)
        primary = mapped.primary_file()
        edge = modrinth_mod_project_datapack_edge_applies(project_type=project.get("project_type"), version=version)
        if edge:
            dependency_records = []
            dependencies = []
        else:
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
        final_kind = "datapack" if edge else mapped.content_kind
        final_placement = "manual_world_creation" if edge else (mapped.content_placement or default_placement_for_kind(mapped.content_kind))
        if edge:
            verified = (minecraft_version == "auto" or minecraft_version in mapped.selected_version.game_versions) and bool(
                primary.url
            ) and bool(primary.hashes)
        else:
            verified = (
                (
                    not modrinth_version_uses_loader_filter(mapped.content_kind)
                    or (modrinth_loader_category(loader) or normalize_loader(loader)) in mapped.selected_version.loaders
                )
                and (minecraft_version == "auto" or minecraft_version in mapped.selected_version.game_versions)
                and bool(primary.url)
                and bool(primary.hashes)
            )
        slug = mapped.slug
        platform_mod = str(project.get("project_type", "")).strip().lower() == "mod"
        url_seg = "mod" if platform_mod else _modrinth_web_segment(final_kind)
        warn_extra = [PLATFORM_MOD_DATAPACK_FILE_WARNING] if edge else []
        base_warn = [] if verified else ["Modrinth metadata was incomplete for autonomous acquisition."]
        return SourceFileCandidate(
            source="modrinth",
            project_id=mapped.project_id,
            file_id=mapped.selected_version.id,
            slug=slug,
            name=mapped.title,
            version_number=mapped.selected_version.version_number,
            minecraft_versions=mapped.selected_version.game_versions,
            loaders=mapped.selected_version.loaders,
            file_name=primary.filename,
            download_url=primary.url,
            page_url=f"https://modrinth.com/{url_seg}/{slug}",
            hashes=primary.hashes,
            file_size_bytes=primary.size,
            dependencies=dependencies,
            dependency_records=dependency_records,
            side="unknown",
            license=project.get("license", {}).get("id") if isinstance(project.get("license"), dict) else project.get("license"),
            distribution_allowed="yes",
            metadata_confidence="high",
            acquisition_status="verified_auto" if verified else "metadata_incomplete",
            warnings=warn_extra + base_warn,
            content_kind=final_kind,
            content_placement=final_placement,
            enabled_by_default=mapped.enabled_by_default,
        )
