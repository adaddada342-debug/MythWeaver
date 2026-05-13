"""Validate downloaded artifacts: Fabric mod jars, duplicate mod IDs, and non-mod zip layouts."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from mythweaver.knowledge.fabric_artifact_policy import slug_or_mod_id_blocked
from mythweaver.schemas.contracts import CandidateMod, ResolvedPack
from mythweaver.validation.fabric_jar_manifest import extract_manifest_fields, read_root_fabric_mod_json
from mythweaver.validation.minecraft_dep_eval import minecraft_dep_supported


def _version_tuple(s: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in re.findall(r"\d+", s):
        try:
            parts.append(int(chunk))
        except ValueError:
            continue
    return tuple(parts) if parts else (0,)


def _version_rank(mod: CandidateMod) -> tuple[int, tuple[int, ...], str]:
    vtype_rank = {"release": 4, "beta": 3, "alpha": 2}.get(mod.selected_version.version_type, 3)
    return (vtype_rank, _version_tuple(mod.selected_version.version_number), mod.selected_version.version_number)


def _content_kind(mod: CandidateMod) -> str:
    return getattr(mod, "content_kind", "mod") or "mod"


def infer_zip_layout_kind(path: Path) -> str | None:
    """Best-effort zip root layout → internal content kind."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = [n.replace("\\", "/") for n in zf.namelist()]
    except (zipfile.BadZipFile, OSError):
        return None
    if any(n.startswith("data/") for n in names):
        return "datapack"
    if any(n == "shaders" or n.startswith("shaders/") for n in names):
        return "shaderpack"
    if any(n.startswith("assets/") for n in names):
        return "resourcepack"
    return None


def inspect_non_mod_row(mod: CandidateMod, path: Path, *, target_minecraft: str) -> dict[str, Any]:
    del target_minecraft  # reserved for future pack_format checks
    kind = _content_kind(mod)
    row: dict[str, Any] = {
        "project_id": mod.project_id,
        "slug": mod.slug,
        "jar_filename": mod.primary_file().filename,
        "jar_path": str(path),
        "content_kind": kind,
    }
    inferred = infer_zip_layout_kind(path)
    row["zip_inferred_kind"] = inferred
    if inferred and inferred != kind:
        row["suspicious_reason"] = "zip_kind_mismatch"
        row["suspicious_detail"] = f"expected {kind}, zip layout looks like {inferred}"
    return row


def inspect_jar_row(
    mod: CandidateMod,
    jar_path: Path,
    *,
    target_minecraft: str,
) -> dict[str, Any]:
    raw = read_root_fabric_mod_json(jar_path)
    row: dict[str, Any] = {
        "project_id": mod.project_id,
        "slug": mod.slug,
        "jar_filename": mod.primary_file().filename,
        "jar_path": str(jar_path),
        "fabric.mod.json_present": raw is not None,
    }
    if not raw:
        row["suspicious_reason"] = "missing_root_fabric_mod_json"
        return row
    fm = extract_manifest_fields(raw)
    row.update(fm)
    mod_id = fm.get("mod_id")
    dm = fm.get("depends_minecraft")

    bloc = slug_or_mod_id_blocked(slug=mod.slug, fabric_mod_id=str(mod_id) if mod_id else None)
    if bloc:
        row["blocked_reason"] = bloc
        return row

    mc_status = minecraft_dep_supported(dm, target_mc=target_minecraft)
    row["minecraft_dep_eval"] = mc_status
    if mc_status == "unsupported":
        row["blocked_reason"] = "fabric_dep_minecraft_range_excludes_target"
    return row


def validate_and_filter_resolved_pack(
    pack: ResolvedPack,
    downloaded_files: dict[str, Path],
    *,
    prefer_project_ids: frozenset[str],
    target_minecraft: str,
) -> tuple[ResolvedPack, dict[str, Path], dict[str, Any], bool]:
    """
    Inspect jars/zips, drop blocklisted / wrong-Minecraft jars, collapse duplicate Fabric mod IDs.

    Returns (filtered_pack, filtered_downloaded_files, report_dict, validation_ok).
    """
    blocked_jars: list[dict[str, Any]] = []
    suspicious_jars: list[dict[str, Any]] = []
    inspection_by_project: dict[str, dict[str, Any]] = {}
    missing_downloaded_jars: list[dict[str, str]] = []

    for mod in pack.selected_mods:
        kind = _content_kind(mod)
        placement = getattr(mod, "content_placement", None)
        if kind == "datapack" and placement == "manual_world_creation":
            inspection_by_project[mod.project_id] = {"skipped": "manual_datapack_not_bundled"}
            continue

        jp = downloaded_files.get(mod.project_id)
        if jp is None or not jp.is_file():
            suspicious_jars.append({"project_id": mod.project_id, "slug": mod.slug, "reason": "missing_downloaded_file"})
            missing_downloaded_jars.append({"project_id": mod.project_id, "slug": mod.slug})
            continue

        if kind == "mod":
            inspection = inspect_jar_row(mod, jp, target_minecraft=target_minecraft)
        else:
            inspection = inspect_non_mod_row(mod, jp, target_minecraft=target_minecraft)

        inspection_by_project[mod.project_id] = inspection
        if inspection.get("blocked_reason"):
            blocked_jars.append(
                {
                    "project_id": mod.project_id,
                    "slug": mod.slug,
                    "fabric_mod_id": inspection.get("mod_id"),
                    "jar_filename": mod.primary_file().filename,
                    "reason": inspection["blocked_reason"],
                }
            )
            continue
        if inspection.get("suspicious_reason"):
            suspicious_jars.append(inspection)

    keep_after_block: list[CandidateMod] = []
    for mod in pack.selected_mods:
        kind = _content_kind(mod)
        placement = getattr(mod, "content_placement", None)
        if kind == "datapack" and placement == "manual_world_creation":
            keep_after_block.append(mod)
            continue
        jp = downloaded_files.get(mod.project_id)
        if jp is None or not jp.is_file():
            continue
        ins = inspection_by_project.get(mod.project_id, {})
        if ins.get("blocked_reason"):
            continue
        keep_after_block.append(mod)

    by_fid: dict[str, list[CandidateMod]] = {}
    unkeyed: list[CandidateMod] = []
    for mod in keep_after_block:
        if _content_kind(mod) != "mod":
            continue
        jp = downloaded_files[mod.project_id]
        raw = read_root_fabric_mod_json(jp)
        if not raw:
            unkeyed.append(mod)
            continue
        fid = raw.get("id")
        if not isinstance(fid, str) or not fid.strip():
            unkeyed.append(mod)
            continue
        by_fid.setdefault(fid.strip(), []).append(mod)

    removed_duplicate_records: list[dict[str, Any]] = []
    duplicate_mod_ids: list[dict[str, Any]] = []
    winner_ids: set[str] = set()

    for fid, group in sorted(by_fid.items(), key=lambda kv: kv[0]):
        if len(group) < 2:
            winner_ids.add(group[0].project_id)
            continue
        duplicate_mod_ids.append(
            {
                "fabric_mod_id": fid,
                "candidates": [
                    {"project_id": m.project_id, "slug": m.slug, "file": m.primary_file().filename} for m in group
                ],
            }
        )

        def sort_key(m: CandidateMod) -> tuple:
            insp = inspection_by_project.get(m.project_id, {})
            mc_ok = {"supported": 3, "unknown": 2, "unsupported": 0}.get(insp.get("minecraft_dep_eval", "unknown"), 2)
            user_pref = 1 if m.project_id in prefer_project_ids else 0
            primary_sel = 0 if m.selection_type == "dependency_added" else 1
            return (mc_ok, user_pref, primary_sel, *_version_rank(m), m.downloads)

        ranked = sorted(group, key=sort_key, reverse=True)
        keeper = ranked[0]
        winner_ids.add(keeper.project_id)
        for loser in ranked[1:]:
            removed_duplicate_records.append(
                {
                    "fabric_mod_id": fid,
                    "kept": {"project_id": keeper.project_id, "slug": keeper.slug},
                    "removed": {"project_id": loser.project_id, "slug": loser.slug, "jar": loser.primary_file().filename},
                }
            )

    for mod in unkeyed:
        if mod.project_id not in winner_ids:
            winner_ids.add(mod.project_id)

    for mod in keep_after_block:
        if _content_kind(mod) != "mod":
            winner_ids.add(mod.project_id)

    new_selected = [m for m in pack.selected_mods if m.project_id in winner_ids]

    new_pack = ResolvedPack(
        name=pack.name,
        minecraft_version=pack.minecraft_version,
        loader=pack.loader,
        loader_version=pack.loader_version,
        selected_mods=new_selected,
        rejected_mods=pack.rejected_mods,
        dependency_edges=pack.dependency_edges,
        conflicts=pack.conflicts,
        config_actions=pack.config_actions,
        artifacts=list(pack.artifacts),
    )

    new_downloaded = {pid: downloaded_files[pid] for pid in winner_ids if pid in downloaded_files}

    wrong_mc = [b for b in blocked_jars if b.get("reason") == "fabric_dep_minecraft_range_excludes_target"]

    report: dict[str, Any] = {
        "status": "passed",
        "target_minecraft": target_minecraft,
        "duplicate_mod_ids": duplicate_mod_ids,
        "wrong_minecraft_version_jars": wrong_mc,
        "suspicious_jars": suspicious_jars,
        "missing_downloaded_jars": missing_downloaded_jars,
        "removed_duplicate_jars": removed_duplicate_records,
        "blocked_jars": blocked_jars,
        "final_mod_count": len(new_selected),
        "initial_mod_count": len(pack.selected_mods),
        "fabric_mod_entries_inspected": len(inspection_by_project),
    }

    ok = True
    if missing_downloaded_jars:
        ok = False
        report["status"] = "failed"
    if len(new_selected) == 0 and len(pack.selected_mods) > 0:
        ok = False
        report["status"] = "failed"
    if any(s.get("suspicious_reason") == "missing_root_fabric_mod_json" for s in suspicious_jars):
        report["mods_missing_fabric_manifest"] = [
            {"project_id": s.get("project_id"), "slug": s.get("slug")}
            for s in suspicious_jars
            if s.get("suspicious_reason") == "missing_root_fabric_mod_json"
        ]
        if report["status"] == "passed":
            report["status"] = "warnings"

    return new_pack, new_downloaded, report, ok


def write_final_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
