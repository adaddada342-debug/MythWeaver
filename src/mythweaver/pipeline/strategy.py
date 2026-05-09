from __future__ import annotations

from mythweaver.pipeline.constraints import (
    apply_profile_constraints,
    capability_terms,
    profile_blocked_terms,
    remove_blocked_values,
)
from mythweaver.pipeline.performance import build_performance_foundation_plan
from mythweaver.schemas.contracts import RequirementProfile, SearchPlan, SearchStrategy


MAX_SEARCH_PLANS = 32


def _append_unique(values: list[str], *items: str) -> None:
    for item in items:
        cleaned = item.strip().lower()
        if cleaned and cleaned not in values:
            values.append(cleaned)


def _has_cold_dying_sun_archetype(profile: RequirementProfile) -> bool:
    text = " ".join(
        profile.themes
        + profile.theme_anchors
        + profile.mood_anchors
        + profile.worldgen_anchors
        + profile.gameplay_anchors
        + profile.required_capabilities
        + profile.preferred_capabilities
        + profile.search_keywords
    )
    return any(
        marker in text
        for marker in ("dying sun", "long nights", "cold apocalypse", "frozen ruins", "weak daylight")
    )


def _weighted_terms(profile: RequirementProfile) -> list[tuple[str, str, float, str]]:
    profile = apply_profile_constraints(profile)
    blocked = profile_blocked_terms(profile)
    weighted: list[tuple[str, str, float, str]] = []
    seen: set[str] = set()

    def add(source_field: str, weight: float, origin: str, *terms: str) -> None:
        for term in remove_blocked_values(terms, blocked):
            cleaned = term.strip().lower()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                weighted.append((cleaned, source_field, weight, origin))

    add("search_keywords", 100.0, "explicit_profile", *profile.search_keywords)
    for capability in profile.required_capabilities:
        add("required_capabilities", 90.0, "explicit_profile", *capability_terms(capability))
    add("theme_anchors", 80.0, "explicit_profile", *profile.theme_anchors)
    add("worldgen_anchors", 78.0, "explicit_profile", *profile.worldgen_anchors)
    add("gameplay_anchors", 76.0, "explicit_profile", *profile.gameplay_anchors)
    add("mood_anchors", 74.0, "explicit_profile", *profile.mood_anchors)
    for capability in profile.preferred_capabilities:
        add("preferred_capabilities", 65.0, "explicit_profile", *capability_terms(capability))

    if _has_cold_dying_sun_archetype(profile):
        add(
            "cold_dying_sun_apocalypse",
            62.0,
            "archetype",
            "winter",
            "cold",
            "frozen",
            "darkness",
            "long nights",
            "undead",
            "ruins",
            "structures",
            "villages",
            "survival",
            "temperature",
            "atmosphere",
            "shaders",
            "performance",
            "dungeons",
            "caves",
        )

    profile_terms: list[str] = []
    for term in profile.themes + profile.desired_systems + profile.terrain + profile.gameplay + profile.mood:
        _append_unique(profile_terms, term)

    text = " ".join(profile_terms)
    if "zombie" in text:
        add("fallback_extraction", 45.0, "fallback_extraction", "zombie", "zombies")
    if "apocalyptic" in text or "wasteland" in text:
        add("fallback_extraction", 40.0, "fallback_extraction", "apocalypse")
        if "wasteland" in text:
            add("fallback_extraction", 40.0, "fallback_extraction", "wasteland")
    if "outback" in text or "desert" in text or "badlands" in text:
        add("fallback_extraction", 40.0, "fallback_extraction", "desert", "outback", "badlands")
    if "ruin" in text or "structure" in text or "abandoned" in text:
        add("fallback_extraction", 38.0, "fallback_extraction", "ruins", "structures", "abandoned")
    if "survival" in text or "scarcity" in text or "scavenging" in text:
        add("fallback_extraction", 36.0, "fallback_extraction", "survival", "scarcity", "thirst", "temperature")
    if "cinematic" in text or "atmosphere" in text or "shader" in text:
        add("fallback_extraction", 34.0, "fallback_extraction", "atmosphere", "shader")
    add("foundation", 31.0, "foundation", "performance", "optimization")
    add("foundation", 30.0, "foundation", *build_performance_foundation_plan(profile).search_targets)
    add("normal_profile", 20.0, "fallback_extraction", *profile_terms)
    if not weighted:
        add("fallback", 10.0, "fallback_extraction", "adventure", "worldgen", "utility", "optimization")
    return weighted


def build_search_strategy(profile: RequirementProfile, *, limit: int = 20) -> SearchStrategy:
    profile = apply_profile_constraints(profile)
    plans: list[SearchPlan] = []
    for term, source_field, weight, origin in _weighted_terms(profile)[:MAX_SEARCH_PLANS]:
        plans.append(
            SearchPlan(
                query=term,
                minecraft_version=profile.minecraft_version,
                loader=profile.loader,
                project_type="mod",
                limit=limit,
                source_field=source_field,
                weight=weight,
                origin=origin,
            )
        )
    if len(plans) < 4:
        for fallback in remove_blocked_values(("adventure", "worldgen", "utility", "optimization"), profile_blocked_terms(profile)):
            if all(plan.query != fallback for plan in plans):
                plans.append(
                    SearchPlan(
                        query=fallback,
                        loader=profile.loader,
                        limit=limit,
                        source_field="fallback",
                        weight=10.0,
                        origin="fallback_extraction",
                    )
                )
            if len(plans) >= 4:
                break
    return SearchStrategy(profile=profile, search_plans=plans[:MAX_SEARCH_PLANS])
