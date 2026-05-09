from __future__ import annotations

import re

from mythweaver.pipeline.constraints import apply_profile_constraints
from mythweaver.schemas.contracts import RequirementProfile

WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")


def _has(words: set[str], *needles: str) -> bool:
    return any(needle in words for needle in needles)


def _contains(text: str, words: set[str], *needles: str) -> bool:
    searchable = text.replace("-", " ")
    for needle in needles:
        normalized = needle.lower().replace("-", " ")
        if " " in normalized:
            if normalized in searchable:
                return True
            continue
        if normalized in words:
            return True
    return False


def _append_unique(values: list[str], *items: str) -> None:
    for item in items:
        if item and item not in values:
            values.append(item)


def _extract_exclusions(text: str) -> list[str]:
    exclusions: list[str] = []
    for term in ("desert", "outback", "badlands", "wasteland", "tropical", "heat survival"):
        if f"no {term}" in text or f"exclude {term}" in text:
            _append_unique(exclusions, term)
    if "winter-only" in text or "winter only" in text or "cold-only" in text or "cold only" in text:
        _append_unique(exclusions, "desert", "outback", "badlands", "tropical", "heat survival")
    return exclusions


def _title_from_prompt(prompt: str) -> str:
    words = [word.capitalize() for word in WORD_RE.findall(prompt.lower())[:4]]
    return " ".join(words) or "Generated Modpack"


def profile_from_prompt(prompt: str) -> RequirementProfile:
    """Deterministic fallback for common fantasy modpack prompts."""

    stripped = prompt.strip()
    if not stripped:
        raise ValueError("prompt must not be empty")
    lowered = stripped.lower()
    words = set(WORD_RE.findall(lowered))
    themes: list[str] = []
    terrain: list[str] = []
    gameplay: list[str] = []
    mood: list[str] = []
    systems: list[str] = []
    search_keywords: list[str] = []
    negative_keywords = _extract_exclusions(lowered)
    explicit_exclusions = list(negative_keywords)

    cold_markers = _contains(
        lowered,
        words,
        "winter",
        "cold",
        "frozen",
        "snow",
        "ice",
        "darkness",
        "long nights",
        "weak daylight",
        "fading daylight",
    )
    dying_sun = _contains(lowered, words, "dying sun", "weak sun", "fading sun", "sun forgot", "weak daylight")
    if dying_sun:
        _append_unique(themes, "dying sun", "cold apocalypse", "long nights")
        _append_unique(mood, "darkness", "gloomy", "atmospheric")
        _append_unique(gameplay, "survival")
        _append_unique(systems, "temperature", "undead", "structures")
        _append_unique(search_keywords, "winter", "cold", "frozen", "darkness", "undead", "survival", "atmosphere")

    if _contains(
        lowered,
        words,
        "apocalypse",
        "apocalyptic",
        "post apocalyptic",
        "post-apocalyptic",
        "wasteland",
        "ruined world",
        "collapse",
        "abandoned world",
        "destroyed civilization",
    ):
        _append_unique(themes, "post-apocalyptic", "survival")
        _append_unique(mood, "desolate", "ruined", "harsh")
        _append_unique(systems, "ruins", "scavenging", "hostile world")
        if _contains(lowered, words, "wasteland", "wastelands"):
            _append_unique(themes, "wasteland")
    if _contains(lowered, words, "zombie", "zombies", "infected", "undead outbreak", "horde", "virus", "infection"):
        _append_unique(themes, "zombie survival")
        _append_unique(gameplay, "combat", "survival", "horde pressure")
        _append_unique(systems, "zombies", "hostile mobs", "infection")
    if _contains(
        lowered,
        words,
        "australia",
        "australian",
        "outback",
        "desert",
        "dry plains",
        "bushland",
        "red sand",
        "harsh heat",
        "drought",
        "arid",
        "scrubland",
    ):
        if not cold_markers:
            _append_unique(themes, "outback", "wasteland")
            _append_unique(terrain, "desert", "dry plains", "sparse vegetation", "wasteland", "badlands")
            _append_unique(gameplay, "survival", "resource scarcity", "heat management")
            _append_unique(mood, "dusty", "isolated", "harsh")
            _append_unique(systems, "temperature")
    if _contains(lowered, words, "heat", "warmth", "keep warm", "heat shelters", "shelter") and cold_markers:
        _append_unique(gameplay, "survival", "shelter")
        _append_unique(systems, "cold_survival", "heat infrastructure", "temperature")
    if _contains(
        lowered,
        words,
        "ruined towns",
        "abandoned towns",
        "ruins",
        "derelict",
        "collapsed buildings",
        "settlements",
        "abandoned villages",
        "overgrown cities",
        "broken roads",
    ):
        _append_unique(systems, "structures", "ruins", "abandoned settlements")
        _append_unique(themes, "lost civilization")
        _append_unique(gameplay, "exploration", "scavenging")
    if _contains(
        lowered,
        words,
        "scarce resources",
        "scarcity",
        "limited supplies",
        "survival",
        "scavenging",
        "thirst",
        "hunger",
        "temperature",
        "heat management",
        "harsh survival",
    ):
        _append_unique(gameplay, "survival", "scavenging", "resource scarcity")
        _append_unique(systems, "thirst", "temperature", "food scarcity", "survival mechanics")
    if _contains(
        lowered,
        words,
        "cinematic",
        "atmospheric",
        "immersive",
        "beautiful",
        "realistic",
        "dusty",
        "foggy",
        "moody",
        "gloomy",
        "dramatic lighting",
    ):
        _append_unique(mood, "cinematic", "atmospheric", "immersive")
        if _contains(lowered, words, "dusty"):
            _append_unique(mood, "dusty")
        _append_unique(systems, "shaders", "atmosphere", "audio/visual enhancement", "fog/weather")

    if _has(words, "winter", "snow", "frozen", "ice"):
        _append_unique(themes, "winter")
        _append_unique(terrain, "snow", "frozen oceans", "mountains")
        _append_unique(systems, "temperature", "weather")
    if _has(words, "horror", "horrifying", "terrifying", "scary", "dark"):
        _append_unique(themes, "horror")
        _append_unique(mood, "dark", "tense")
        _append_unique(systems, "hostile mobs")
    if _has(words, "survival", "hardcore", "scarcity"):
        _append_unique(gameplay, "survival", "resource scarcity")
    if _has(words, "ruins", "structures", "villages", "kingdoms", "cities"):
        _append_unique(systems, "structures")
        _append_unique(terrain, "villages")
    if _has(words, "fantasy", "magic", "rpg", "kingdoms"):
        _append_unique(themes, "fantasy", "magic")
        _append_unique(gameplay, "rpg", "exploration")
        _append_unique(systems, "quests")
    if _has(words, "cozy", "peaceful"):
        _append_unique(mood, "cozy", "peaceful")
    if _has(words, "farming", "farm", "crops"):
        _append_unique(gameplay, "farming")
        _append_unique(systems, "crops")
    if _has(words, "dragon", "dragons"):
        _append_unique(themes, "dragons")
        _append_unique(systems, "dragons")
    if _has(words, "anime", "apocalypse", "god", "boss"):
        _append_unique(themes, "anime", "apocalypse")
        _append_unique(gameplay, "combat progression", "boss fights")
        _append_unique(systems, "skills", "bosses")

    if not themes:
        _append_unique(themes, "adventure")
    if not gameplay:
        _append_unique(gameplay, "exploration")
    if not systems:
        _append_unique(systems, "quality of life")

    profile = RequirementProfile(
        name=_title_from_prompt(stripped),
        prompt=stripped,
        themes=themes,
        terrain=terrain,
        gameplay=gameplay,
        mood=mood,
        desired_systems=systems,
        search_keywords=search_keywords,
        negative_keywords=negative_keywords,
        explicit_exclusions=explicit_exclusions,
        loader="fabric",
        minecraft_version="auto",
    )
    return apply_profile_constraints(profile)
