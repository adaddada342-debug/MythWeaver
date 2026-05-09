from __future__ import annotations

from mythweaver.schemas.contracts import SourceFileCandidate, SourceSearchResult


class PlanetMinecraftSourceProvider:
    source_name = "planetminecraft"
    trust_tier = "manual_only"

    def is_configured(self) -> bool:
        return True

    async def search(self, query: str, *, minecraft_version: str, loader: str, limit: int = 20) -> SourceSearchResult:
        return SourceSearchResult(
            query=query,
            source=self.source_name,
            warnings=["Planet Minecraft entries require manual review before autonomous build."],
        )

    async def inspect(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        return SourceFileCandidate(
            source="planetminecraft",
            slug=project_ref.rstrip("/").split("/")[-1] or None,
            name=project_ref,
            page_url=project_ref if project_ref.startswith("http") else None,
            minecraft_versions=[],
            loaders=[],
            metadata_confidence="low",
            acquisition_status="verified_manual_required",
            warnings=[
                "Planet Minecraft entries require manual review before autonomous build.",
                "No stable dependency, loader, version, hash, or download safety metadata is assumed.",
            ],
        )

    async def resolve_file(self, project_ref: str, *, minecraft_version: str, loader: str) -> SourceFileCandidate | None:
        return await self.inspect(project_ref, minecraft_version=minecraft_version, loader=loader)
