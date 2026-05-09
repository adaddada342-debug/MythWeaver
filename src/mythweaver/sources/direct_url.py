from __future__ import annotations

from mythweaver.schemas.contracts import SourceFileCandidate, SourceSearchResult


class DirectUrlSourceProvider:
    source_name = "direct_url"
    trust_tier = "unsafe"

    def is_configured(self) -> bool:
        return True

    async def search(self, query: str, *, minecraft_version: str, loader: str, limit: int = 20) -> SourceSearchResult:
        return SourceSearchResult(query=query, source=self.source_name, warnings=["Direct URL sources require explicit refs and are blocked by default."])

    async def inspect(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        return SourceFileCandidate(
            source="direct_url",
            name=project_ref,
            download_url=project_ref,
            acquisition_status="download_blocked",
            metadata_confidence="low",
            warnings=["Direct URLs are manual/risky and are not automatically downloaded without explicit allow flags and hash verification."],
        )

    async def resolve_file(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        return await self.inspect(project_ref, minecraft_version=minecraft_version, loader=loader)
