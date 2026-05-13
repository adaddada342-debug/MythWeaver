"""Curated slug/mod-id denylists and heuristic filters for Fabric artifact sanity."""

from __future__ import annotations

import re

ARTIFACT_SLUG_DENYLIST: frozenset[str] = frozenset(
    {
        "craft_slime_fabric",
        "craftable-gunpowder-for-fabric",
        "craftable-slime-for-fabric",
        "nofabric",
        "neko-fabric-hacks",
        "bedrockminer",
        "autofish",
        "fakenameportfabric",
        "acceleratedrendering",
    }
)


def normalized_slug_denylist() -> frozenset[str]:
    """Expose a copy-ish view for callers that may extend at runtime."""
    return ARTIFACT_SLUG_DENYLIST


def slug_or_mod_id_blocked(*, slug: str, fabric_mod_id: str | None) -> str | None:
    s = slug.strip().lower()
    if s in ARTIFACT_SLUG_DENYLIST:
        return "artifact_slug_curated_blocklist"
    fid = (fabric_mod_id or "").strip().lower()
    if fid and fid in ARTIFACT_SLUG_DENYLIST:
        return "artifact_mod_id_curated_blocklist"
    return None


CRAFTABLE_VANILLA_SLUG_HINT = re.compile(
    r"(^|-)(craftable|craft-)(iron|gold|diamond|emerald|netherite|bundle|horse|armor|gunpowder|slime)(\b|-)",
    re.I,
)


def shallow_search_blocked(
    *,
    slug: str,
    title: str,
    version_number: str,
    autofish_explicitly_requested: bool = False,
    hacks_explicitly_requested: bool = False,
) -> str | None:
    """Return rejection reason string or None when the hit should not be curated automatically."""
    s = slug.lower()
    ttl = title.lower()

    if not hacks_explicitly_requested and (re.search(r"\bhacks?\b", s) or re.search(r"\bhacks?\b", ttl)):
        return "filter_keyword_hack"
    if not autofish_explicitly_requested and (re.search(r"\bautofish\b", s) or "auto fish" in ttl):
        return "filter_keyword_autofish"

    if version_number.startswith("0.0.1"):
        # tiny placeholder releases — keep only verified dependency chains elsewhere
        return "filter_placeholder_version"

    # duplicate craft-X-for-fabric family (beyond explicit blocklist entries)
    if s.startswith("craftable-") and s.endswith("-for-fabric"):
        return "filter_craftable_vanilla_fork"
    if CRAFTABLE_VANILLA_SLUG_HINT.search(s):
        return "filter_resource_craftable_slug"

    return slug_or_mod_id_blocked(slug=slug, fabric_mod_id=None)
