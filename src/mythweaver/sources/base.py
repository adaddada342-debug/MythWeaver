from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from mythweaver.schemas.contracts import SourceFileCandidate, SourceSearchResult


@runtime_checkable
class SourceProvider(Protocol):
    source_name: str
    trust_tier: Literal["official_api", "semi_trusted", "manual_only", "unsafe"]

    def is_configured(self) -> bool:
        ...

    async def search(
        self,
        query: str,
        *,
        minecraft_version: str,
        loader: str,
        limit: int = 20,
    ) -> SourceSearchResult:
        ...

    async def inspect(
        self,
        project_ref: str,
        *,
        minecraft_version: str,
        loader: str,
    ) -> SourceFileCandidate | None:
        ...

    async def resolve_file(
        self,
        project_ref: str,
        *,
        minecraft_version: str,
        loader: str,
    ) -> SourceFileCandidate | None:
        ...
