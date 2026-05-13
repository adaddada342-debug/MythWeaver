from __future__ import annotations

from mythweaver.pipeline.constraints import capability_terms, infer_candidate_capabilities, text_matches_terms
from mythweaver.schemas.contracts import CandidateMod, CandidateSelection, RejectedMod

CAPABILITY_GROUPS = {
    "performance": {"optimization", "performance", "lithium", "ferritecore", "modernfix", "krypton", "lazydfu"},
    "worldgen": {"worldgen", "biomes", "terrain"},
    "structures": {"structures", "village", "ruins", "dungeon"},
    "mobs": {"mobs", "creatures", "boss"},
    "survival": {"survival", "temperature", "weather", "food"},
    "magic": {"magic", "rpg", "skills", "quests"},
    "utility": {"utility", "map", "storage", "inventory"},
    "atmosphere": {"atmosphere", "sound", "visual", "ambience"},
}

EXCLUSIVE_GROUPS = {
    "shader_loader": {"iris", "oculus", "shader loader", "shaders mod", "shader support"},
    "renderer_optimization": {"sodium", "embeddium", "rubidium", "canvas", "renderer replacement", "renderer optimization"},
    "minimap": {"minimap", "xaero", "journeymap"},
    "temperature_system": {"temperature", "thirst", "tough as nails", "dehydration"},
}

GROUP_LIMITS = {
    "worldgen": 2,
    "structures": 2,
    "mobs": 2,
    "survival": 2,
    "magic": 2,
    "utility": 3,
    "atmosphere": 2,
    "shader_loader": 1,
    "renderer_optimization": 1,
    "minimap": 1,
    "temperature_system": 1,
}

NOVELTY_TERMS = {
    "disc",
    "chicken",
    "meme",
    "joke",
    "funny",
    "tiny",
    "addon only",
    "cosmetic only",
    "wallpaper",
    "overlay",
    "single item",
}

PERFORMANCE_MINIMUM_CAPABILITIES = {
    "renderer_optimization",
    "logic_optimization",
    "memory_optimization",
    "entity_culling",
}

PILLAR_DEFINITIONS = {
    "volcanic_worldgen": {
        "capabilities": {"volcanic_worldgen", "mountains", "lava_caves", "basalt_biomes", "caves"},
        "required": False,
        "budget_min": 1,
        "budget_max": 4,
    },
    "ruins_structures": {
        "capabilities": {"ruins", "structures", "forts", "temples", "abandoned_mines"},
        "required": True,
        "budget_min": 1,
        "budget_max": 5,
    },
    "exploration_dungeons": {
        "capabilities": {"dungeons", "exploration", "hostile_mobs"},
        "required": True,
        "budget_min": 1,
        "budget_max": 4,
    },
    "villages_frontier": {
        "capabilities": {"villages", "outposts", "frontier_villages", "village_expansion"},
        "required": False,
        "budget_min": 0,
        "budget_max": 3,
    },
    "survival_progression": {
        "capabilities": {"survival_progression", "resource_scarcity", "temperature", "food_scarcity"},
        "required": False,
        "budget_min": 0,
        "budget_max": 3,
    },
    "atmosphere_visuals": {
        "capabilities": {"atmosphere", "ambient_sounds", "shader_support"},
        "required": False,
        "budget_min": 1,
        "budget_max": 3,
    },
    "performance_foundation": {
        "capabilities": {"renderer_optimization", "logic_optimization", "memory_optimization", "entity_culling", "performance_foundation"},
        "required": True,
        "budget_min": 3,
        "budget_max": 6,
    },
}


def _groups(candidate: CandidateMod) -> set[str]:
    text = candidate.searchable_text()
    categories = set(candidate.categories)
    found: set[str] = set()
    for group, markers in CAPABILITY_GROUPS.items():
        if categories & markers or any(marker in text for marker in markers):
            found.add(group)
    return found or {"general"}


def _exclusive_groups(candidate: CandidateMod) -> set[str]:
    text = candidate.searchable_text()
    found: set[str] = set()
    for group, markers in EXCLUSIVE_GROUPS.items():
        if any(marker in text for marker in markers):
            found.add(group)
    return found


def is_novelty_candidate(candidate: CandidateMod) -> bool:
    return bool(text_matches_terms(candidate.searchable_text(), NOVELTY_TERMS))


def _candidate_capabilities(candidate: CandidateMod) -> set[str]:
    return set(candidate.matched_capabilities) | set(infer_candidate_capabilities(candidate))


def _capability_evidence(candidate: CandidateMod, capability: str) -> bool:
    capabilities = _candidate_capabilities(candidate)
    if capability in capabilities:
        return True
    return bool(text_matches_terms(candidate.searchable_text(), capability_terms(capability)))


def _pillar_for_candidate(candidate: CandidateMod) -> str | None:
    capabilities = _candidate_capabilities(candidate)
    for pillar, definition in PILLAR_DEFINITIONS.items():
        if capabilities & definition["capabilities"]:
            return pillar
    return None


def _performance_coverage(candidates: list[CandidateMod]) -> set[str]:
    covered: set[str] = set()
    for candidate in candidates:
        capabilities = _candidate_capabilities(candidate)
        covered.update(capabilities & PERFORMANCE_MINIMUM_CAPABILITIES)
    return covered


def _performance_required(profile) -> bool:
    return "performance_foundation" in profile.required_capabilities or profile.foundation_policy.performance == "enabled"


def _pillar_required(profile, pillar: str, definition: dict[str, object]) -> bool:
    capabilities = definition["capabilities"]
    if pillar == "performance_foundation":
        return _performance_required(profile)
    return bool(set(profile.required_capabilities) & capabilities)


def _strict_candidate_score(candidate: CandidateMod, profile) -> tuple[int, float]:
    capabilities = _candidate_capabilities(candidate)
    required = len(capabilities & set(profile.required_capabilities))
    preferred = len(capabilities & set(profile.preferred_capabilities))
    novelty = 1 if is_novelty_candidate(candidate) else 0
    return (required * 100 + preferred * 25 - novelty * 80, candidate.score.total)


def _add_candidate(
    candidate: CandidateMod,
    selected: list[CandidateMod],
    selected_ids: set[str],
    group_counts: dict[str, int],
    rejected: list[RejectedMod],
    *,
    enforce_groups: bool,
) -> bool:
    if candidate.project_id in selected_ids or candidate.score.hard_reject_reason:
        return False
    groups = _groups(candidate) | _exclusive_groups(candidate)
    duplicate_groups = [
        group
        for group in groups
        if group != "general" and group_counts.get(group, 0) >= GROUP_LIMITS.get(group, 99)
    ]
    if enforce_groups and duplicate_groups:
        rejected.append(
            RejectedMod(
                project_id=candidate.project_id,
                title=candidate.title,
                reason="duplicate_capability_group",
                detail=", ".join(sorted(duplicate_groups)),
            )
        )
        return False
    selected.append(candidate)
    selected_ids.add(candidate.project_id)
    for group in groups:
        group_counts[group] = group_counts.get(group, 0) + 1
    return True


def _select_strict(candidates: list[CandidateMod], profile, *, max_mods: int) -> CandidateSelection:
    selected: list[CandidateMod] = []
    selected_ids: set[str] = set()
    group_counts: dict[str, int] = {}
    rejected: list[RejectedMod] = []
    viable = [candidate for candidate in candidates if not candidate.score.hard_reject_reason]
    required_caps = [cap for cap in profile.required_capabilities if cap not in {"performance_foundation"}]
    for capability in required_caps:
        matches = [candidate for candidate in viable if _capability_evidence(candidate, capability)]
        matches.sort(key=lambda candidate: _strict_candidate_score(candidate, profile), reverse=True)
        for candidate in matches:
            if _add_candidate(candidate, selected, selected_ids, group_counts, rejected, enforce_groups=False):
                break

    if _performance_required(profile):
        for capability in sorted(PERFORMANCE_MINIMUM_CAPABILITIES):
            matches = [candidate for candidate in viable if _capability_evidence(candidate, capability)]
            matches.sort(key=lambda candidate: _strict_candidate_score(candidate, profile), reverse=True)
            for candidate in matches:
                if _add_candidate(candidate, selected, selected_ids, group_counts, rejected, enforce_groups=False):
                    break

    pillar_counts: dict[str, int] = {}
    for candidate in selected:
        pillar = _pillar_for_candidate(candidate)
        if pillar:
            pillar_counts[pillar] = pillar_counts.get(pillar, 0) + 1

    remaining = [candidate for candidate in viable if candidate.project_id not in selected_ids]
    remaining.sort(key=lambda candidate: _strict_candidate_score(candidate, profile), reverse=True)
    for candidate in remaining:
        if len(selected) >= max_mods:
            rejected.append(RejectedMod(project_id=candidate.project_id, title=candidate.title, reason="max_mods_exceeded"))
            continue
        pillar = _pillar_for_candidate(candidate)
        if is_novelty_candidate(candidate) and selected:
            rejected.append(
                RejectedMod(
                    project_id=candidate.project_id,
                    title=candidate.title,
                    reason="novelty_penalty_applied",
                    detail="micro_or_novelty_mod_not_core_to_profile",
                )
            )
            continue
        if pillar and pillar_counts.get(pillar, 0) >= PILLAR_DEFINITIONS[pillar]["budget_max"]:
            rejected.append(
                RejectedMod(
                    project_id=candidate.project_id,
                    title=candidate.title,
                    reason="pillar_budget_exceeded",
                    detail=pillar,
                )
            )
            continue
        if _add_candidate(candidate, selected, selected_ids, group_counts, rejected, enforce_groups=True):
            if pillar:
                pillar_counts[pillar] = pillar_counts.get(pillar, 0) + 1

    coverage: dict[str, dict[str, object]] = {}
    for pillar, definition in PILLAR_DEFINITIONS.items():
        required = _pillar_required(profile, pillar, definition)
        selected_for_pillar = [
            candidate.project_id
            for candidate in selected
            if _candidate_capabilities(candidate) & definition["capabilities"]
        ]
        budget_min = int(definition["budget_min"]) if required else 0
        coverage[pillar] = {
            "required": required,
            "capabilities": sorted(definition["capabilities"]),
            "budget_min": budget_min,
            "budget_max": definition["budget_max"],
            "selected_candidates": selected_for_pillar,
            "satisfied": len(selected_for_pillar) >= budget_min,
            "missing_reason": "" if len(selected_for_pillar) >= budget_min else "no selected candidate covered this pillar",
        }
    performance_gaps = sorted(PERFORMANCE_MINIMUM_CAPABILITIES - _performance_coverage(selected)) if _performance_required(profile) else []
    if performance_gaps:
        coverage["performance_foundation"]["satisfied"] = False
        coverage["performance_foundation"]["missing_reason"] = "missing " + ", ".join(performance_gaps)

    return CandidateSelection(
        selected_project_ids=[candidate.project_id for candidate in selected],
        rejected_mods=rejected,
        pillar_coverage=coverage,
        novelty_mods_selected=[candidate.project_id for candidate in selected if is_novelty_candidate(candidate)],
        performance_foundation_gaps=performance_gaps,
        overrepresented_concepts=[
            pillar for pillar, count in pillar_counts.items() if count > PILLAR_DEFINITIONS.get(pillar, {}).get("budget_max", 99)
        ],
    )


def select_candidates(candidates: list[CandidateMod], *, max_mods: int, profile=None, strict_profile_mode: bool = False) -> CandidateSelection:
    if strict_profile_mode and profile is not None:
        return _select_strict(candidates, profile, max_mods=max_mods)

    selected: list[CandidateMod] = []
    selected_ids: set[str] = set()
    group_counts: dict[str, int] = {}
    rejected: list[RejectedMod] = []

    for candidate in candidates:
        if len(selected) >= max_mods:
            rejected.append(
                RejectedMod(project_id=candidate.project_id, title=candidate.title, reason="max_mods_exceeded")
            )
            continue
        groups = _groups(candidate) | _exclusive_groups(candidate)
        duplicate_groups = [
            group
            for group in groups
            if group != "general" and group_counts.get(group, 0) >= GROUP_LIMITS.get(group, 99)
        ]
        if duplicate_groups:
            rejected.append(
                RejectedMod(
                    project_id=candidate.project_id,
                    title=candidate.title,
                    reason="duplicate_capability_group",
                    detail=", ".join(sorted(duplicate_groups)),
                )
            )
            continue
        selected.append(candidate)
        selected_ids.add(candidate.project_id)
        for group in groups:
            group_counts[group] = group_counts.get(group, 0) + 1

    return CandidateSelection(selected_project_ids=[candidate.project_id for candidate in selected], rejected_mods=rejected)
