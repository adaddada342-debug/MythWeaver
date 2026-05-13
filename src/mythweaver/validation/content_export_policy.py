"""Centralized warnings for mixed content kinds (mods, datapacks, RP, shaders)."""

from __future__ import annotations

from mythweaver.catalog.modrinth_datapack_edge import PLATFORM_MOD_DATAPACK_FILE_WARNING
from mythweaver.schemas.contracts import CandidateMod, ResolvedPack


def collect_content_export_warnings(selected_mods: list[CandidateMod]) -> list[str]:
    """Return non-fatal warnings (e.g. Sodium + shaderpack without Iris)."""
    warnings: list[str] = []
    slugs = {m.slug.lower() for m in selected_mods}
    titles = " ".join(m.title.lower() for m in selected_mods)
    has_sodium = "sodium" in slugs or "sodium" in titles
    has_iris = "iris" in slugs or "iris" in titles
    has_shaderpack = any(getattr(m, "content_kind", "mod") == "shaderpack" for m in selected_mods)
    if has_shaderpack and has_sodium and not has_iris:
        warnings.append(
            "Shader pack(s) are selected alongside Sodium but Iris was not detected in the list; "
            "players typically need Iris (or equivalent) on Fabric for shader packs."
        )
    for m in selected_mods:
        if getattr(m, "content_kind", "mod") == "datapack" and getattr(m, "content_placement", None) == "manual_world_creation":
            if m.slug:
                warnings.append(
                    f"Datapack `{m.slug}` uses manual world-creation placement and is not auto-bundled into exports; "
                    "install it into a world's `datapacks` folder when creating a new world."
                )
        if (
            str(getattr(m, "platform_project_type", "") or "").strip().lower() == "mod"
            and getattr(m, "content_kind", "mod") == "datapack"
            and getattr(m, "content_placement", None) == "manual_world_creation"
        ):
            warnings.append(PLATFORM_MOD_DATAPACK_FILE_WARNING)
    return warnings


def jjthunder_guidance_lines(selected_mods: list[CandidateMod]) -> list[str]:
    """Fixed guidance when JJThunder-style worldgen packs are detected (safe string heuristics)."""
    hits = []
    for m in selected_mods:
        blob = f"{m.slug} {m.title}".lower()
        if "jjthunder" in blob or "to the max" in blob:
            hits.append(m.slug or m.project_id)
    if not hits:
        return []
    slug_list = ", ".join(sorted(set(hits)))
    return [
        f"JJThunder-style content detected ({slug_list}).",
        "- **New worlds only** — install this pack during world creation; do not add it to existing worlds.",
        "- Do **not** combine with Terralith, Tectonic, or William Wythers' Overworld in the same world unless you designed for that.",
        "- **High worldgen performance risk** — profile before scaling render distance or enabling shaders.",
        "- Use **Chunky** (or equivalent) for pregeneration when exploring large areas.",
        "- Start with **render distance 8–10** and **simulation distance 5–6**, then tune upward only after stable FPS.",
        "- Keep **shaders disabled** until baseline stability is proven.",
    ]


def content_sections_dict(pack: ResolvedPack) -> dict[str, list[dict[str, str]]]:
    """Structured JSON for MCP consumers."""
    sections: dict[str, list[dict[str, str]]] = {
        "mods": [],
        "datapacks": [],
        "resourcepacks": [],
        "shaderpacks": [],
        "manual_world_creation": [],
    }
    for m in pack.selected_mods:
        kind = getattr(m, "content_kind", "mod")
        row = {"slug": m.slug, "title": m.title, "project_id": m.project_id}
        if kind == "mod":
            sections["mods"].append(row)
        elif kind == "datapack":
            sections["datapacks"].append(row)
            if getattr(m, "content_placement", None) == "manual_world_creation":
                sections["manual_world_creation"].append(row)
        elif kind == "resourcepack":
            sections["resourcepacks"].append(row)
        elif kind == "shaderpack":
            sections["shaderpacks"].append(row)
    return sections
