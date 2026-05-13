"""Normalize SelectedModList.mods + SelectedModList.content into a single verification list."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mythweaver.catalog.content_kinds import ContentKind, ContentPlacement, default_placement_for_kind
from mythweaver.schemas.contracts import PackContentEntry, SelectedModEntry, SelectedModList, SelectedModRole

SourceKey = Literal["modrinth", "curseforge", "auto"]


@dataclass(frozen=True)
class NormalizedSelectionRow:
    """One logical row after merging `mods` and `content`."""

    ref: str
    source: SourceKey
    kind: ContentKind
    placement: ContentPlacement | None
    required: bool
    enabled_by_default: bool | None
    reason_selected: str | None
    role: SelectedModRole
    notes: tuple[str, ...]
    from_content: bool


def _entry_kind(entry: SelectedModEntry) -> ContentKind:
    return entry.kind or "mod"


def _entry_source(entry: SelectedModEntry) -> SourceKey:
    """Non-mod rows must use official APIs (Modrinth or CurseForge). Legacy mod rows keep Modrinth-first behavior."""
    kind = _entry_kind(entry)
    src = entry.source
    if src == "auto":
        return "auto"
    if kind != "mod" and src not in ("modrinth", "curseforge"):
        raise ValueError(
            f"selected entry kind {kind!r} requires source modrinth or curseforge (got {src!r})",
        )
    if src == "curseforge":
        return "curseforge"
    return "modrinth"


def _normalize_pack_content_entry(entry: PackContentEntry) -> NormalizedSelectionRow:
    placement = entry.placement if entry.placement is not None else default_placement_for_kind(entry.kind)
    enabled = entry.enabled_by_default
    if entry.kind == "shaderpack" and enabled is None:
        enabled = False
    return NormalizedSelectionRow(
        ref=entry.slug.strip(),
        source=entry.source,
        kind=entry.kind,
        placement=placement,
        required=entry.required,
        enabled_by_default=enabled,
        reason_selected=entry.reason,
        role="theme",
        notes=tuple(entry.notes),
        from_content=True,
    )


def _normalize_mod_entry(entry: SelectedModEntry) -> NormalizedSelectionRow:
    kind = _entry_kind(entry)
    placement = entry.placement if entry.placement is not None else default_placement_for_kind(kind)
    enabled = entry.enabled_by_default
    if kind == "shaderpack" and enabled is None:
        enabled = False
    return NormalizedSelectionRow(
        ref=entry.identifier().strip(),
        source=_entry_source(entry),
        kind=kind,
        placement=placement,
        required=entry.required,
        enabled_by_default=enabled,
        reason_selected=entry.reason_selected,
        role=entry.role,
        notes=tuple(),
        from_content=False,
    )


def normalized_selection_rows(selected: SelectedModList) -> list[NormalizedSelectionRow]:
    rows: list[NormalizedSelectionRow] = []
    for entry in selected.mods:
        rows.append(_normalize_mod_entry(entry))
    for entry in selected.content:
        rows.append(_normalize_pack_content_entry(entry))
    return rows


def selection_row_count(selected: SelectedModList) -> int:
    return len(selected.mods) + len(selected.content)
