"""Build CandidateMod instances from CurseForge mod + file metadata (official API)."""

from __future__ import annotations

from typing import Any

from mythweaver.catalog.content_kinds import ContentKind, ContentPlacement
from mythweaver.schemas.contracts import CandidateMod, DependencyRecord, DependencyType, ModFile, ModVersion


def _cf_dep_type(relation_type: Any) -> DependencyType:
    if relation_type == 2:
        return "optional"
    if relation_type == 3:
        return "required"
    if relation_type == 4:
        return "incompatible"
    if relation_type == 5:
        return "embedded"
    return "required"


def _cf_hashes(file_obj: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in file_obj.get("hashes", []) or []:
        if item.get("algo") == 1 and item.get("value"):
            out["sha1"] = str(item["value"])
        elif item.get("algo") == 2 and item.get("value"):
            out["md5"] = str(item["value"])
    return {k: v for k, v in out.items() if v}


def candidate_mod_from_curseforge(
    mod: dict[str, Any],
    file_obj: dict[str, Any],
    *,
    content_kind: ContentKind,
    content_placement: ContentPlacement | None,
    platform_class_id: int | None,
    selection_type: str,
    why_selected: list[str],
) -> CandidateMod:
    raw_url = file_obj.get("downloadUrl")
    url = raw_url if isinstance(raw_url, str) and raw_url.startswith("https://") else ""
    if not url:
        raise ValueError("CurseForge file is missing an HTTPS downloadUrl")
    fname = str(file_obj.get("fileName") or "download.zip")
    hashes = _cf_hashes(file_obj)
    if not hashes.get("sha1") and not hashes.get("sha512"):
        raise ValueError("CurseForge file is missing sha1/sha512 hash metadata")
    mf = ModFile(filename=fname, url=url, hashes=hashes, size=int(file_obj.get("fileLength") or 0), primary=True)
    gvs = [str(v).lower() for v in file_obj.get("gameVersions", []) if str(v)[0].isdigit()]
    loaders = [
        str(v).lower()
        for v in file_obj.get("gameVersions", [])
        if v and str(v) and not str(v)[0].isdigit()
    ]
    deps = [
        DependencyRecord(
            project_id=str(d.get("modId")),
            dependency_type=_cf_dep_type(d.get("relationType")),
        )
        for d in file_obj.get("dependencies", [])
        if d.get("modId")
    ]
    mv = ModVersion(
        id=str(file_obj.get("id")),
        project_id=str(mod.get("id")),
        version_number=str(file_obj.get("displayName") or file_obj.get("fileName") or file_obj.get("id")),
        game_versions=gvs or ["auto"],
        loaders=list(dict.fromkeys(loaders)) or ["unknown"],
        version_type="release",
        status="listed",
        dependencies=deps,
        files=[mf],
    )
    mod_id = str(mod.get("id") or "")
    categories: list[str] = []
    for c in mod.get("categories") or []:
        if isinstance(c, dict) and c.get("name"):
            categories.append(str(c["name"]).lower())
        elif isinstance(c, str):
            categories.append(c.lower())
    return CandidateMod(
        project_id=mod_id,
        slug=str(mod.get("slug") or mod_id),
        title=str(mod.get("name") or mod_id),
        description=str(mod.get("summary") or ""),
        categories=categories,
        client_side="unknown",
        server_side="unknown",
        downloads=int(mod.get("downloadCount") or 0),
        follows=int(mod.get("downloadCount") or 0),
        loaders=list(dict.fromkeys(loaders)) if loaders else ["unknown"],
        game_versions=gvs,
        selected_version=mv,
        dependency_count=len(deps),
        selection_type=selection_type,  # type: ignore[arg-type]
        why_selected=why_selected,
        content_kind=content_kind,
        content_placement=content_placement,
        platform_project_type=str(platform_class_id) if platform_class_id is not None else None,
    )
