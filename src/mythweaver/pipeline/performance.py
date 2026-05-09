from __future__ import annotations

from mythweaver.schemas.contracts import (
    FoundationTarget,
    PerformanceFoundationReport,
    RequirementProfile,
    ShaderRecommendation,
    ShaderRecommendationSet,
)

PERFORMANCE_OPT_OUT_PHRASES = (
    "no performance mods",
    "don't add optimization mods",
    "dont add optimization mods",
    "vanilla performance only",
    "no sodium",
)

SHADER_OPT_OUT_PHRASES = (
    "no shaders",
    "no iris",
    "don't add shaders",
    "dont add shaders",
)

FOUNDATION_CAPABILITIES: dict[str, dict[str, list[str]]] = {
    "fabric": {
        "fabric_api_or_loader_library": ["fabric api"],
        "renderer_optimization": ["sodium"],
        "game_logic_optimization": ["lithium"],
        "memory_optimization": ["ferritecore", "modernfix"],
        "rendering_ui_optimization": ["immediatelyfast"],
        "entity_culling": ["entityculling"],
        "networking_optimization": ["krypton"],
        "startup_optimization": ["lazydfu"],
        "mod_menu": ["mod menu"],
        "shader_support": ["iris shaders"],
    },
    "forge": {
        "renderer_optimization": ["renderer optimization"],
        "game_logic_optimization": ["game logic optimization"],
        "memory_optimization": ["memory optimization"],
        "entity_culling": ["entity culling"],
        "networking_optimization": ["network optimization"],
        "mod_menu": ["mod menu"],
        "shader_support": ["shader support"],
    },
    "neoforge": {
        "renderer_optimization": ["renderer optimization"],
        "game_logic_optimization": ["game logic optimization"],
        "memory_optimization": ["memory optimization"],
        "entity_culling": ["entity culling"],
        "networking_optimization": ["network optimization"],
        "mod_menu": ["mod menu"],
        "shader_support": ["shader support"],
    },
    "quilt": {
        "fabric_api_or_loader_library": ["quilted fabric api"],
        "renderer_optimization": ["sodium"],
        "game_logic_optimization": ["lithium"],
        "memory_optimization": ["ferritecore"],
        "entity_culling": ["entityculling"],
        "mod_menu": ["mod menu"],
        "shader_support": ["iris shaders"],
    },
}


def _prompt_text(profile: RequirementProfile) -> str:
    return " ".join(
        [
            profile.prompt or "",
            " ".join(profile.themes),
            " ".join(profile.terrain),
            " ".join(profile.gameplay),
            " ".join(profile.mood),
            " ".join(profile.desired_systems),
            " ".join(profile.search_keywords),
            " ".join(profile.theme_anchors),
            " ".join(profile.mood_anchors),
            " ".join(profile.worldgen_anchors),
            " ".join(profile.gameplay_anchors),
            " ".join(profile.required_capabilities),
            " ".join(profile.preferred_capabilities),
        ]
    ).lower()


def _matched_phrases(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase in text]


def _shader_category(profile: RequirementProfile) -> str:
    text = _prompt_text(profile)
    if any(token in text for token in ("dying sun", "weak sun", "long nights", "cold apocalypse", "frozen", "winter", "cold")):
        return "cold_cinematic_gloom"
    if any(token in text for token in ("outback", "desert", "dusty")):
        return "apocalyptic_dusty"
    if "apocalypse" in text and "wasteland" in text:
        return "apocalyptic_dusty"
    if any(token in text for token in ("horror", "gloomy", "dark", "zombie")):
        return "gloomy_horror"
    if any(token in text for token in ("cozy", "peaceful", "fantasy")):
        return "cozy_fantasy"
    if any(token in text for token in ("vibrant", "adventure", "beautiful")):
        return "vibrant_adventure"
    if profile.performance_target == "low-end":
        return "low_end_performance"
    return "cinematic_realistic"


def shader_recommendations_for_profile(profile: RequirementProfile, *, enabled: bool = True) -> ShaderRecommendationSet:
    if not enabled:
        return ShaderRecommendationSet(install_reason="Shader recommendations disabled by prompt opt-out.")
    category = _shader_category(profile)
    primary_by_category = {
        "cold_cinematic_gloom": ShaderRecommendation(
            name="Complementary Reimagined",
            category="cold_cinematic_gloom",
            reason="Cold, gloomy, cinematic presets with fog and controlled saturation fit a dying-sun winter pack.",
        ),
        "apocalyptic_dusty": ShaderRecommendation(
            name="Complementary Reimagined",
            category="apocalyptic_dusty",
            reason="Desaturated lighting and readable atmosphere fit dusty survival without extreme hardware cost.",
        ),
        "gloomy_horror": ShaderRecommendation(
            name="MakeUp Ultra Fast",
            category="gloomy_horror",
            reason="Flexible contrast, fog, and low-end presets work for horror packs.",
        ),
        "cozy_fantasy": ShaderRecommendation(
            name="Complementary Reimagined",
            category="cozy_fantasy",
            reason="Warm fantasy lighting with broad compatibility.",
        ),
        "vibrant_adventure": ShaderRecommendation(
            name="BSL Shaders",
            category="vibrant_adventure",
            reason="Popular vibrant adventure look.",
        ),
        "low_end_performance": ShaderRecommendation(
            name="MakeUp Ultra Fast",
            category="low_end_performance",
            reason="Performance-oriented presets are suitable for modest machines.",
        ),
        "cinematic_realistic": ShaderRecommendation(
            name="Complementary Reimagined",
            category="cinematic_realistic",
            reason="A balanced cinematic default with good compatibility.",
        ),
    }
    return ShaderRecommendationSet(
        primary=primary_by_category[category],
        backups=[
            ShaderRecommendation(
                name="BSL Shaders",
                category="backup_known_popular",
                reason="Known popular backup for a brighter cinematic look.",
            ),
            ShaderRecommendation(
                name="Complementary Unbound",
                category="backup_known_popular",
                reason="Known popular backup for stronger cinematic lighting.",
            ),
        ],
        low_end_fallback=ShaderRecommendation(
            name="MakeUp Ultra Fast",
            category="low_end_performance",
            reason="Low-end fallback recommendation when shader cost matters.",
        ),
        installed=False,
        install_reason="Not bundled by default; install only from a verified allowed source/license.",
    )


def build_performance_foundation_plan(profile: RequirementProfile) -> PerformanceFoundationReport:
    text = _prompt_text(profile)
    performance_opt_out = _matched_phrases(text, PERFORMANCE_OPT_OUT_PHRASES)
    shader_opt_out = _matched_phrases(text, SHADER_OPT_OUT_PHRASES)
    performance_enabled = profile.foundation_policy.performance != "disabled" and not performance_opt_out
    shader_support_enabled = profile.foundation_policy.shaders != "disabled" and not shader_opt_out
    utilities_enabled = profile.foundation_policy.utilities != "disabled"
    loader_capabilities = FOUNDATION_CAPABILITIES.get(profile.loader, {})

    targets: list[FoundationTarget] = []
    if performance_enabled:
        for capability, queries in loader_capabilities.items():
            if capability == "shader_support":
                continue
            if capability == "mod_menu" and not utilities_enabled:
                continue
            targets.append(
                FoundationTarget(
                    capability=capability,
                    queries=queries,
                    loader=profile.loader,
                    required=capability == "fabric_api_or_loader_library",
                    budget_role="utility" if capability == "mod_menu" else "foundation",
                )
            )
    if shader_support_enabled and "shader_support" in loader_capabilities:
        targets.append(
            FoundationTarget(
                capability="shader_support",
                queries=loader_capabilities["shader_support"],
                loader=profile.loader,
                budget_role="visual",
            )
        )

    search_targets: list[str] = []
    for target in targets:
        for query in target.queries:
            if query not in search_targets:
                search_targets.append(query)

    return PerformanceFoundationReport(
        performance_enabled=performance_enabled,
        shader_support_enabled=shader_support_enabled,
        loader=profile.loader,
        targets=targets,
        search_targets=search_targets,
        opt_out_phrases=performance_opt_out + shader_opt_out,
        shader_recommendations=shader_recommendations_for_profile(profile, enabled=shader_support_enabled),
    )
