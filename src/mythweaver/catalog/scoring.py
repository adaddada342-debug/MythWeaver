from __future__ import annotations

import math
import re

from mythweaver.pipeline.constraints import (
    candidate_exclusion_matches,
    candidate_forbidden_capability_matches,
    candidate_negative_matches,
    capability_terms,
)
from mythweaver.schemas.contracts import CandidateMod, ModScore, RequirementProfile

WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")
PERFORMANCE_CATEGORIES = {"optimization", "fabric", "utility", "performance"}
HEAVY_CATEGORIES = {"worldgen", "biomes", "mobs", "technology", "adventure", "magic"}
FOUNDATION_MARKERS = {
    "sodium",
    "lithium",
    "ferritecore",
    "immediatelyfast",
    "entityculling",
    "modernfix",
    "krypton",
    "lazydfu",
    "fabric api",
    "mod menu",
    "iris",
}


def _tokens(values: list[str]) -> set[str]:
    found: set[str] = set()
    for value in values:
        found.update(WORD_RE.findall(value.lower()))
    return found


def _hard_reject(candidate: CandidateMod, profile: RequirementProfile) -> str | None:
    if candidate_exclusion_matches(candidate, profile):
        return "explicit_exclusion"
    if candidate_forbidden_capability_matches(candidate, profile):
        return "forbidden_capability"
    if profile.loader not in candidate.loaders and profile.loader not in candidate.selected_version.loaders:
        return "loader_mismatch"
    if profile.minecraft_version != "auto" and profile.minecraft_version not in candidate.game_versions:
        if profile.minecraft_version not in candidate.selected_version.game_versions:
            return "minecraft_version_mismatch"
    if candidate.selected_version.status not in {"listed", "unlisted"}:
        return "version_status_not_installable"
    try:
        candidate.primary_file()
    except ValueError:
        return "missing_download_file"
    return None


def _relevance(candidate: CandidateMod, profile: RequirementProfile) -> tuple[float, list[str]]:
    desired = _tokens(
        profile.themes
        + profile.terrain
        + profile.gameplay
        + profile.mood
        + profile.desired_systems
        + profile.search_keywords
        + profile.theme_anchors
        + profile.mood_anchors
        + profile.worldgen_anchors
        + profile.gameplay_anchors
    )
    for capability in profile.required_capabilities + profile.preferred_capabilities:
        desired.update(_tokens(capability_terms(capability)))
    if not desired:
        return 0.0, []
    text = candidate.searchable_text()
    matched = [token for token in sorted(desired) if token in text]
    score = min(45.0, len(matched) * 9.0)
    reasons = [f"theme:{token}" for token in matched[:8]]
    return score, reasons


def _quality(candidate: CandidateMod) -> float:
    downloads = min(20.0, math.log10(max(candidate.downloads, 1)) * 4.0)
    follows = min(10.0, math.log10(max(candidate.follows, 1)) * 2.5)
    release_bonus = 5.0 if candidate.selected_version.version_type == "release" else 1.0
    return downloads + follows + release_bonus


def _performance(candidate: CandidateMod, profile: RequirementProfile) -> float:
    categories = set(candidate.categories)
    text = candidate.searchable_text()
    if profile.performance_target == "low-end" and categories & HEAVY_CATEGORIES:
        return -8.0
    if any(marker in text for marker in FOUNDATION_MARKERS):
        return 14.0
    if categories & PERFORMANCE_CATEGORIES:
        return 8.0
    return 0.0


def score_candidate(candidate: CandidateMod, profile: RequirementProfile) -> CandidateMod:
    reject_reason = _hard_reject(candidate, profile)
    if reject_reason:
        candidate.score = ModScore(hard_reject_reason=reject_reason, total=-10_000.0)
        return candidate

    relevance, reasons = _relevance(candidate, profile)
    quality = _quality(candidate)
    compatibility = 20.0
    performance = _performance(candidate, profile)
    dependency_penalty = min(18.0, candidate.dependency_count * 3.0)
    negative_matches = candidate_negative_matches(candidate, profile)
    negative_penalty = 18.0 * len(negative_matches)
    total = relevance + quality + compatibility + performance - dependency_penalty - negative_penalty
    if candidate.selected_version.version_type != "release":
        reasons.append(f"version_type:{candidate.selected_version.version_type}")
    if dependency_penalty:
        reasons.append(f"dependency_penalty:{dependency_penalty:g}")
    if negative_penalty:
        reasons.append(f"negative_constraint_penalty:{negative_penalty:g}")
    candidate.score = ModScore(
        total=round(total, 3),
        relevance=round(relevance, 3),
        quality=round(quality, 3),
        compatibility=compatibility,
        performance=performance,
        dependency_penalty=dependency_penalty,
        reasons=reasons,
    )
    return candidate


def score_candidates(
    candidates: list[CandidateMod], profile: RequirementProfile
) -> list[CandidateMod]:
    scored = [score_candidate(candidate, profile) for candidate in candidates]
    return sorted(scored, key=lambda candidate: candidate.score.total, reverse=True)
