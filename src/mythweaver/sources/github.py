from __future__ import annotations

from mythweaver.schemas.contracts import SourceFileCandidate, SourceSearchResult


class GitHubReleaseSourceProvider:
    source_name = "github"
    trust_tier = "semi_trusted"

    def is_configured(self) -> bool:
        return True

    async def search(self, query: str, *, minecraft_version: str, loader: str, limit: int = 20) -> SourceSearchResult:
        return SourceSearchResult(query=query, source=self.source_name, warnings=["GitHub broad search is disabled; use explicit repository/release refs."])

    async def inspect(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        return SourceFileCandidate(
            source="github",
            name=project_ref,
            page_url=project_ref if project_ref.startswith("http") else None,
            acquisition_status="metadata_incomplete",
            metadata_confidence="low",
            warnings=["GitHub release assets require explicit trust plus jar metadata/hash validation before autonomous use."],
        )

    async def resolve_file(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        return await self.inspect(project_ref, minecraft_version=minecraft_version, loader=loader)
