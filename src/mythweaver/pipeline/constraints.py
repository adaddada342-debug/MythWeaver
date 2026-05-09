from __future__ import annotations

import re
from typing import Iterable

from mythweaver.schemas.contracts import CandidateMod, RequirementProfile

WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")

DESERT_LIKE_TERMS = {
    "desert",
    "outback",
    "badlands",
    "arid",
    "tropical",
    "heat survival",
    "summer",
}

FORBIDDEN_CAPABILITY_TERMS: dict[str, set[str]] = {
    "desert_worldgen": {"desert", "badlands", "arid", "dunes", "mesa"},
    "outback": {"outback", "bushland", "red sand", "scrubland"},
    "tropical_worldgen": {"tropical", "jungle", "rainforest"},
    "modern_transit": {"mtr", "metro", "train", "trains", "transit", "railway", "london underground"},
    "trains": {"train", "trains", "railway", "metro", "mtr", "london underground"},
    "vehicles": {"vehicle", "vehicles", "car", "cars", "train", "trains", "railway", "metro"},
    "industrial_automation": {"create", "automation", "factory", "machinery", "industrial", "assembly line"},
    "modern_ui_overlay": {"windows", "windowsstartingoverlay", "start menu", "overlay", "ui overlay", "startingoverlay"},
    "wallpaper_cosmetic": {"wallpaper", "wall paper"},
    "guns": {"gun", "guns", "firearms", "rifle", "pistol"},
    "space": {"space", "rocket", "planet", "nuclear", "sci fi", "sci-fi"},
    "sci_fi": {"sci fi", "sci-fi", "space", "laser", "nuclear"},
}

CAPABILITY_TERMS: dict[str, set[str]] = {
    "volcanic_worldgen": {"volcano", "volcanic", "ash", "ashfall", "lava", "basalt"},
    "mountains": {"mountain", "mountains", "cliff", "cliffs", "peaks"},
    "lava_caves": {"lava cave", "lava caves", "lava", "cave", "caves"},
    "basalt_biomes": {"basalt", "biome", "biomes"},
    "forts": {"fort", "forts", "fortress", "fortresses"},
    "abandoned_mines": {"abandoned mine", "abandoned mines", "mine", "mines", "mineshaft", "mineshafts"},
    "villages": {"village", "villages", "settlement", "settlements"},
    "outposts": {"outpost", "outposts"},
    "frontier_villages": {"frontier", "village", "villages", "outpost", "outposts"},
    "hostile_mobs": {"hostile", "mob", "mobs", "monster", "monsters"},
    "temperature": {"temperature", "heat", "warmth", "cold"},
    "food_scarcity": {"food", "hunger", "scarcity"},
    "renderer_optimization": {"sodium", "renderer", "rendering", "embeddium"},
    "logic_optimization": {"lithium", "logic", "server optimization"},
    "memory_optimization": {"ferritecore", "ferrite", "modernfix", "memory"},
    "entity_culling": {"entityculling", "entity culling", "culling"},
    "mod_menu": {"mod menu", "modmenu"},
    "forest_worldgen": {"forest", "forests", "biome", "biomes", "woodland", "grove"},
    "overgrown_nature": {"overgrown", "nature", "reclaimed", "moss", "roots", "vines"},
    "moss": {"moss", "mossy"},
    "roots": {"root", "roots", "rooted"},
    "mushroom_biomes": {"mushroom", "mushrooms", "fungal", "fungus"},
    "underground_biomes": {"underground", "cave", "caves", "caverns", "subterranean"},
    "caves": {"cave", "caves", "cavern", "caverns", "underground"},
    "ruins": {"ruin", "ruins", "ruined", "buried", "abandoned"},
    "temples": {"temple", "temples", "sanctuary", "sanctuaries"},
    "nature_magic": {"nature magic", "magic", "druid", "druidic", "botanical"},
    "ambient_sounds": {"ambient", "ambience", "sound", "sounds", "audio"},
    "village_expansion": {"village", "villages", "settlement", "settlements"},
    "survival_progression": {"survival", "progression", "scarcity"},
    "cold_survival": {"cold", "winter", "frozen", "snow", "temperature", "warmth", "shelter"},
    "structures": {"structures", "structure", "ruins", "villages", "dungeons", "settlements", "temples", "towers"},
    "undead": {"undead", "zombie", "zombies", "skeleton", "horde"},
    "performance_foundation": {"performance", "optimization", "sodium", "lithium", "ferritecore", "modernfix", "entityculling"},
    "shader_support": {"shader", "shaders", "iris"},
    "village_defense": {"village", "villages", "defense", "guard"},
    "atmosphere": {"atmosphere", "fog", "weather", "ambience", "sound"},
    "fog_weather": {"fog", "weather", "mist"},
    "exploration": {"exploration", "discover", "discovery"},
    "dungeons": {"dungeons", "dungeon"},
    "waystones": {"waystones", "waystone"},
    "maps": {"maps", "map", "minimap", "atlas"},
    "resource_scarcity": {"scarcity", "scavenging", "resources"},
    "modern_transit": {"mtr", "metro", "train", "trains", "transit", "railway", "london underground"},
    "trains": {"train", "trains", "railway", "metro", "mtr"},
    "vehicles": {"vehicle", "vehicles", "car", "cars", "train", "trains"},
    "industrial_automation": {"create", "automation", "factory", "machinery", "industrial"},
    "modern_ui_overlay": {"windows", "windowsstartingoverlay", "start menu", "overlay", "ui overlay", "startingoverlay"},
    "wallpaper_cosmetic": {"wallpaper", "wall paper"},
    "guns": {"gun", "guns", "firearms", "rifle", "pistol"},
    "space": {"space", "rocket", "planet", "nuclear", "sci fi", "sci-fi"},
    "desert_worldgen": {"desert", "badlands", "arid", "dunes", "mesa"},
}


def normalize_term(value: str) -> str:
    return " ".join(WORD_RE.findall(value.lower().replace("-", " ")))


def normalized_terms(values: Iterable[str]) -> list[str]:
    terms: list[str] = []
    for value in values:
        normalized = normalize_term(value)
        if normalized and normalized not in terms:
            terms.append(normalized)
    return terms


def profile_blocked_terms(profile: RequirementProfile) -> set[str]:
    blocked = set(normalized_terms(profile.negative_keywords + profile.explicit_exclusions))
    for capability in profile.forbidden_capabilities:
        blocked.update(FORBIDDEN_CAPABILITY_TERMS.get(capability, {normalize_term(capability)}))
    if any(anchor in normalized_terms(profile.themes + profile.theme_anchors) for anchor in ("winter", "cold apocalypse")):
        blocked.update(term for term in DESERT_LIKE_TERMS if term not in normalized_terms(profile.search_keywords))
    return {term for term in blocked if term}


def domain_blocklist_terms(profile: RequirementProfile) -> set[str]:
    blocked = set(profile_blocked_terms(profile))
    text = " ".join(
        normalized_terms(
            profile.themes
            + profile.search_keywords
            + profile.required_capabilities
            + profile.preferred_capabilities
            + profile.theme_anchors
            + profile.worldgen_anchors
            + profile.gameplay_anchors
        )
    )
    if any(term in text for term in ("forest", "overgrown", "roots", "moss", "mushroom", "fungal", "caves")):
        blocked.update(
            {
                "modern city",
                "transit",
                "train",
                "trains",
                "railway",
                "metro",
                "mtr",
                "london underground",
                "create",
                "automation",
                "industrial",
                "machinery",
                "factory",
                "wallpaper",
                "overlay",
                "windows",
                "startingoverlay",
                "guns",
                "vehicles",
                "space",
                "nuclear",
                "sci fi",
                "sci-fi",
                "desert",
                "outback",
            }
        )
    return blocked


def text_matches_terms(text: str, terms: Iterable[str]) -> list[str]:
    normalized_text = normalize_term(text)
    words = set(WORD_RE.findall(normalized_text))
    matches: list[str] = []
    for term in terms:
        normalized = normalize_term(term)
        if not normalized:
            continue
        if " " in normalized:
            if normalized in normalized_text:
                matches.append(normalized)
        elif normalized in words:
            matches.append(normalized)
    return list(dict.fromkeys(matches))


def remove_blocked_values(values: Iterable[str], blocked_terms: Iterable[str]) -> list[str]:
    blocked = set(normalized_terms(blocked_terms))
    kept: list[str] = []
    for value in values:
        normalized = normalize_term(value)
        if not normalized:
            continue
        if normalized in blocked:
            continue
        if any(term in normalized for term in blocked):
            continue
        if value not in kept:
            kept.append(value)
    return kept


def apply_profile_constraints(profile: RequirementProfile) -> RequirementProfile:
    blocked = profile_blocked_terms(profile)
    updates = {
        "themes": remove_blocked_values(profile.themes, blocked),
        "terrain": remove_blocked_values(profile.terrain, blocked),
        "gameplay": remove_blocked_values(profile.gameplay, blocked),
        "mood": remove_blocked_values(profile.mood, blocked),
        "desired_systems": remove_blocked_values(profile.desired_systems, blocked),
        "search_keywords": remove_blocked_values(profile.search_keywords, blocked),
        "theme_anchors": remove_blocked_values(profile.theme_anchors, blocked),
        "mood_anchors": remove_blocked_values(profile.mood_anchors, blocked),
        "worldgen_anchors": remove_blocked_values(profile.worldgen_anchors, blocked),
        "gameplay_anchors": remove_blocked_values(profile.gameplay_anchors, blocked),
        "preferred_capabilities": remove_blocked_values(profile.preferred_capabilities, blocked),
    }
    return profile.model_copy(update=updates)


def candidate_exclusion_matches(candidate: CandidateMod, profile: RequirementProfile) -> list[str]:
    return text_matches_terms(candidate.searchable_text(), profile.explicit_exclusions)


def candidate_negative_matches(candidate: CandidateMod, profile: RequirementProfile) -> list[str]:
    blocked = profile_blocked_terms(profile)
    return text_matches_terms(candidate.searchable_text(), blocked)


def candidate_forbidden_capability_matches(candidate: CandidateMod, profile: RequirementProfile) -> list[str]:
    matches: list[str] = []
    text = candidate.searchable_text()
    for capability in profile.forbidden_capabilities:
        terms = FORBIDDEN_CAPABILITY_TERMS.get(capability, {capability})
        if text_matches_terms(text, terms):
            matches.append(capability)
    return matches


def capability_terms(capability: str) -> list[str]:
    terms = CAPABILITY_TERMS.get(capability, {capability.replace("_", " ")})
    return sorted(terms)


def infer_candidate_capabilities(candidate: CandidateMod) -> list[str]:
    text = candidate.searchable_text()
    found: list[str] = []
    for capability, terms in CAPABILITY_TERMS.items():
        if text_matches_terms(text, terms):
            found.append(capability)
    return list(dict.fromkeys(found))


def profile_positive_terms(profile: RequirementProfile) -> list[str]:
    terms: list[str] = []
    for value in (
        profile.search_keywords
        + profile.theme_anchors
        + profile.worldgen_anchors
        + profile.gameplay_anchors
        + profile.mood_anchors
        + profile.themes
        + profile.terrain
        + profile.gameplay
        + profile.desired_systems
    ):
        normalized = normalize_term(value)
        if normalized:
            terms.append(normalized)
    for capability in profile.required_capabilities + profile.preferred_capabilities:
        terms.extend(capability_terms(capability))
    return list(dict.fromkeys(terms))


def candidate_positive_evidence(candidate: CandidateMod, profile: RequirementProfile) -> tuple[list[str], list[str]]:
    terms = text_matches_terms(candidate.searchable_text(), profile_positive_terms(profile))
    capabilities = [
        capability
        for capability in infer_candidate_capabilities(candidate)
        if capability in set(profile.required_capabilities + profile.preferred_capabilities)
    ]
    return terms, capabilities
