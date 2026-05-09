from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mythweaver.schemas.contracts import CandidateMod


EMPTY_MEMORY = {
    "successful_packs": [],
    "failed_packs": [],
    "repair_attempts": [],
    "signals": {
        "known_good_together": [],
        "known_bad_together": [],
        "renderer_stack_success": [],
        "shader_stack_success": [],
        "dependency_chain_success": [],
        "crash_suspect_count": {},
    },
}


class CompatibilityMemory:
    """Advisory local memory; never replaces Modrinth verification."""

    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir) / "knowledge" / "local"
        self.path = self.root / "compatibility_memory.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(EMPTY_MEMORY))
        data = json.loads(self.path.read_text(encoding="utf-8"))
        merged = json.loads(json.dumps(EMPTY_MEMORY))
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        return merged

    def save(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def record_manual_success(
        self,
        *,
        name: str,
        minecraft_version: str,
        loader: str,
        mods: list[str],
        note: str,
        confidence: str = "high",
    ) -> None:
        self._record_success(
            name=name,
            minecraft_version=minecraft_version,
            loader=loader,
            mods=mods,
            dependency_added_mods=[],
            validation_status="manual_success",
            source="user_manual_validation",
            confidence=confidence,
            notes=note,
        )

    def record_successful_pack(
        self,
        *,
        name: str,
        minecraft_version: str,
        loader: str,
        mods: list[str],
        dependency_added_mods: list[str],
        validation_status: str,
        notes: str,
    ) -> None:
        self._record_success(
            name=name,
            minecraft_version=minecraft_version,
            loader=loader,
            mods=mods,
            dependency_added_mods=dependency_added_mods,
            validation_status=validation_status,
            source="automatic_launch_validation",
            confidence="high",
            notes=notes,
        )

    def _record_success(
        self,
        *,
        name: str,
        minecraft_version: str,
        loader: str,
        mods: list[str],
        dependency_added_mods: list[str],
        validation_status: str,
        source: str,
        confidence: str,
        notes: str,
    ) -> None:
        data = self.load()
        entry = {
            "pack_name": name,
            "minecraft_version": minecraft_version,
            "loader": loader,
            "mods": sorted(set(mods)),
            "dependency_added_mods": sorted(set(dependency_added_mods)),
            "build_timestamp": _now(),
            "launch_status": "success",
            "validation_status": validation_status,
            "source": source,
            "confidence": confidence,
            "notes": notes,
        }
        data["successful_packs"].append(entry)
        data["signals"]["known_good_together"].append(
            {"minecraft_version": minecraft_version, "loader": loader, "mods": entry["mods"], "source": source}
        )
        foundation = [mod for mod in entry["mods"] if mod in {"sodium", "lithium", "ferrite-core", "iris", "indium", "entityculling", "immediatelyfast", "krypton"}]
        if foundation:
            data["signals"]["renderer_stack_success"].append(
                {"minecraft_version": minecraft_version, "loader": loader, "mods": foundation, "source": source}
            )
        self.save(data)

    def record_failed_pack(
        self,
        *,
        name: str,
        minecraft_version: str,
        loader: str,
        mods: list[str],
        failed_stage: str,
        crash_classification: str,
        suspected_mods: list[str],
        suggested_fixes: list[str],
        log_paths: list[str],
    ) -> None:
        data = self.load()
        entry = {
            "pack_name": name,
            "minecraft_version": minecraft_version,
            "loader": loader,
            "mods": sorted(set(mods)),
            "failed_stage": failed_stage,
            "crash_classification": crash_classification,
            "suspected_mods": sorted(set(suspected_mods)),
            "suggested_fixes": suggested_fixes,
            "log_paths": log_paths,
            "build_timestamp": _now(),
        }
        data["failed_packs"].append(entry)
        if suspected_mods:
            data["signals"]["known_bad_together"].append(
                {
                    "minecraft_version": minecraft_version,
                    "loader": loader,
                    "mods": sorted(set(suspected_mods)),
                    "classification": crash_classification,
                }
            )
            for mod in suspected_mods:
                counts = data["signals"]["crash_suspect_count"]
                counts[mod] = counts.get(mod, 0) + 1
        self.save(data)

    def record_repair_plan(
        self,
        *,
        pack_name: str,
        minecraft_version: str,
        loader: str,
        crash_classification: str,
        suspected_mods: list[str],
        option_ids: list[str],
    ) -> None:
        data = self.load()
        data["repair_attempts"].append(
            {
                "event": "repair_options_generated",
                "pack_name": pack_name,
                "minecraft_version": minecraft_version,
                "loader": loader,
                "crash_classification": crash_classification,
                "suspected_mods": sorted(set(suspected_mods)),
                "option_ids": option_ids,
                "timestamp": _now(),
            }
        )
        if suspected_mods:
            data["signals"]["known_bad_together"].append(
                {
                    "minecraft_version": minecraft_version,
                    "loader": loader,
                    "mods": sorted(set(suspected_mods)),
                    "classification": crash_classification,
                    "source": "repair_plan",
                }
            )
        self.save(data)

    def record_repair_applied(
        self,
        *,
        pack_name: str,
        minecraft_version: str,
        loader: str,
        option_id: str,
        action_type: str,
        target_slug: str | None,
    ) -> None:
        data = self.load()
        data["repair_attempts"].append(
            {
                "event": "repair_option_applied",
                "pack_name": pack_name,
                "minecraft_version": minecraft_version,
                "loader": loader,
                "option_id": option_id,
                "action_type": action_type,
                "target_slug": target_slug,
                "timestamp": _now(),
            }
        )
        self.save(data)

    def hints_for_mods(self, *, mods: list[str], minecraft_version: str, loader: str) -> dict[str, Any]:
        selected = set(_normalize_mod_id(mod) for mod in mods if mod)
        data = self.load()
        good = [
            entry
            for entry in data["signals"].get("known_good_together", [])
            if _same_target(entry, minecraft_version, loader) and selected & set(entry.get("mods", []))
        ]
        risks = [
            entry
            for entry in data["signals"].get("known_bad_together", [])
            if _same_target(entry, minecraft_version, loader) and set(entry.get("mods", [])).issubset(selected)
        ]
        renderer_success = [
            entry
            for entry in data["signals"].get("renderer_stack_success", [])
            if _same_target(entry, minecraft_version, loader) and set(entry.get("mods", [])).issubset(selected)
        ]
        return {
            "known_good_matches": good,
            "known_risk_matches": risks,
            "renderer_stack_success": renderer_success,
            "warnings": [
                "Local compatibility memory has a previous failure for this mod combination."
                for _ in risks[:1]
            ],
            "confidence_adjustment": 0.1 if good or renderer_success else 0.0,
        }

    def hints_for_candidates(self, candidates: list[CandidateMod], *, minecraft_version: str, loader: str) -> dict[str, Any]:
        return self.hints_for_mods(
            mods=[candidate.slug for candidate in candidates] + [candidate.project_id for candidate in candidates],
            minecraft_version=minecraft_version,
            loader=loader,
        )


def _same_target(entry: dict[str, Any], minecraft_version: str, loader: str) -> bool:
    return entry.get("minecraft_version") == minecraft_version and entry.get("loader", "").lower() == loader.lower()


def _normalize_mod_id(value: str) -> str:
    return value.strip().lower()


def _now() -> str:
    return datetime.now(UTC).isoformat()
