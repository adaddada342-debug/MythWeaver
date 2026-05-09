from __future__ import annotations

from mythweaver.pipeline.constraints import (
    candidate_exclusion_matches,
    candidate_forbidden_capability_matches,
    candidate_positive_evidence,
    domain_blocklist_terms,
    infer_candidate_capabilities,
    text_matches_terms,
)
from mythweaver.schemas.contracts import CandidateMod, RejectedMod


class SanitizationResult:
    def __init__(self, candidates: list[CandidateMod], rejected: list[RejectedMod]) -> None:
        self.candidates = candidates
        self.rejected = rejected


def _profile_requests(capability: str, profile) -> bool:
    requested = set(profile.required_capabilities + profile.preferred_capabilities)
    text = " ".join(
        profile.search_keywords
        + profile.themes
        + profile.desired_systems
        + profile.theme_anchors
        + profile.worldgen_anchors
        + profile.gameplay_anchors
    )
    if capability in requested:
        return True
    if capability == "industrial_automation":
        return any(term in text for term in ("create", "automation", "industrial", "factory", "machinery"))
    if capability in {"modern_transit", "trains", "vehicles"}:
        return any(term in text for term in ("train", "metro", "railway", "transit", "vehicle"))
    return False


def _rejection_reason(capabilities: list[str], blocked_terms: list[str]) -> str:
    if any(capability in capabilities for capability in ("modern_transit", "trains", "vehicles")):
        return "transit_vehicle_rejected"
    if "industrial_automation" in capabilities:
        return "industrial_automation_rejected"
    if any(capability in capabilities for capability in ("modern_ui_overlay", "wallpaper_cosmetic")):
        return "ui_wallpaper_overlay_rejected"
    if blocked_terms:
        return "domain_blocklist_match"
    return "forbidden_capability_match"


def sanitize_candidates_for_profile(
    candidates: list[CandidateMod],
    profile,
    *,
    strict_profile_mode: bool,
) -> SanitizationResult:
    kept: list[CandidateMod] = []
    rejected: list[RejectedMod] = []
    blocked_terms = domain_blocklist_terms(profile)

    for candidate in candidates:
        capabilities = infer_candidate_capabilities(candidate)
        explicit_matches = candidate_exclusion_matches(candidate, profile)
        forbidden_matches = [
            capability
            for capability in candidate_forbidden_capability_matches(candidate, profile)
            if not _profile_requests(capability, profile)
        ]
        domain_matches = [
            term
            for term in text_matches_terms(candidate.searchable_text(), blocked_terms)
            if not (
                term in {"create", "automation", "industrial", "factory", "machinery"}
                and _profile_requests("industrial_automation", profile)
            )
        ]
        blocked_capabilities = [
            capability
            for capability in capabilities
            if capability
            in {
                "modern_transit",
                "trains",
                "vehicles",
                "industrial_automation",
                "modern_ui_overlay",
                "wallpaper_cosmetic",
                "guns",
                "space",
                "desert_worldgen",
            }
            and not _profile_requests(capability, profile)
        ]

        if explicit_matches:
            rejected.append(
                RejectedMod(
                    project_id=candidate.project_id,
                    title=candidate.title,
                    reason="explicit_exclusion_match",
                    detail=", ".join(explicit_matches),
                )
            )
            continue
        if blocked_capabilities or domain_matches:
            reason = _rejection_reason(blocked_capabilities, domain_matches)
            rejected.append(
                RejectedMod(
                    project_id=candidate.project_id,
                    title=candidate.title,
                    reason=reason,
                    detail=", ".join(blocked_capabilities + domain_matches),
                )
            )
            continue
        if forbidden_matches:
            rejected.append(
                RejectedMod(
                    project_id=candidate.project_id,
                    title=candidate.title,
                    reason="forbidden_capability_match",
                    detail=", ".join(forbidden_matches),
                )
            )
            continue

        matched_terms, matched_capabilities = candidate_positive_evidence(candidate, profile)
        if strict_profile_mode and not matched_terms and not matched_capabilities:
            rejected.append(
                RejectedMod(
                    project_id=candidate.project_id,
                    title=candidate.title,
                    reason="low_theme_relevance",
                    detail="No required/preferred capability, anchor, or high-priority search keyword matched.",
                )
            )
            continue

        candidate.matched_profile_terms = matched_terms
        candidate.matched_capabilities = matched_capabilities
        candidate.why_selected = [
            f"matched_terms:{', '.join(matched_terms[:6])}" if matched_terms else "",
            f"matched_capabilities:{', '.join(matched_capabilities[:6])}" if matched_capabilities else "",
        ]
        candidate.why_selected = [reason for reason in candidate.why_selected if reason]
        candidate.penalties_applied = []
        candidate.rejection_risk = None
        kept.append(candidate)

    return SanitizationResult(kept, rejected)
