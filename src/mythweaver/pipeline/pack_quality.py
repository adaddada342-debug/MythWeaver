from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable

from mythweaver.schemas.contracts import (
    CandidateMod,
    GameplayLoop,
    Loader,
    ModBlueprintSlot,
    PackBlueprint,
    PackDesign,
    PackDesignPillar,
    PackDesignReviewIssue,
    PackDesignReviewReport,
    ProgressionPhase,
    ReviewIssue,
    SelectedModList,
)


@dataclass(frozen=True)
class ArchetypeProfile:
    required_systems: tuple[str, ...]
    recommended_systems: tuple[str, ...] = ()
    forbidden_or_risky_systems: tuple[str, ...] = ()
    quality_bar: tuple[str, ...] = ()
    common_failure_modes: tuple[str, ...] = ()
    default_core_loops: tuple[GameplayLoop, ...] = field(default_factory=tuple)
    default_progression_phases: tuple[ProgressionPhase, ...] = field(default_factory=tuple)


def _loop(name: str, description: str, actions: list[str], rewards: list[str]) -> GameplayLoop:
    return GameplayLoop(name=name, description=description, repeated_player_actions=actions, reward_types=rewards)


def _phase(name: str, purpose: str, systems: list[str], rewards: list[str]) -> ProgressionPhase:
    return ProgressionPhase(
        name=name,
        purpose=purpose,
        expected_player_actions=["learn the current tools", "complete one concrete objective"],
        required_systems=systems,
        reward_types=rewards,
    )


ARCHETYPE_PROFILES: dict[str, ArchetypeProfile] = {
    "vanilla_plus": ArchetypeProfile(
        required_systems=("performance_foundation", "client_qol", "inventory_management"),
        recommended_systems=("atmosphere", "light_worldgen_or_structures", "building_blocks"),
        forbidden_or_risky_systems=("tech", "automation", "large_magic_progression", "boss_progression", "too_many_content_systems"),
        quality_bar=("Feels like Minecraft with better friction, not a new game.", "Avoid power creep and content bloat."),
        common_failure_modes=("stops being vanilla+", "power creep", "bloat"),
        default_core_loops=(_loop("Polished Vanilla Loop", "Gather, build, explore, and return home with lower friction.", ["explore nearby", "improve base", "craft QoL upgrades"], ["comfort", "new building options"]),),
        default_progression_phases=(_phase("Early Comfort", "Make normal survival smoother without replacing it.", ["client_qol", "inventory_management"], ["less friction"]),),
    ),
    "rpg_adventure": ArchetypeProfile(
        required_systems=("performance_foundation", "quest_book", "exploration_tools", "dungeon_progression", "loot_progression", "gear_upgrade_path", "boss_progression"),
        recommended_systems=("skill_tree", "magic_system", "waypoints_or_fast_travel", "atmosphere"),
        quality_bar=("Dungeons, loot, bosses, and quests should reinforce one adventure arc.", "Endgame must be visible before the pack is built."),
        common_failure_modes=("random dungeons with no reason", "no endgame", "bosses not connected to loot or quests"),
        default_core_loops=(_loop("Adventure Loop", "Use quests to find dangerous places, improve gear, and defeat stronger threats.", ["follow quests", "raid dungeons", "upgrade gear"], ["loot", "boss access"]),),
        default_progression_phases=(_phase("Quested Exploration", "Teach the route from first dungeon to boss goals.", ["quest_book", "dungeon_progression"], ["loot_progression"]), _phase("Boss Ladder", "Connect gear and bosses into replayable milestones.", ["boss_progression", "gear_upgrade_path"], ["endgame_goal"])),
    ),
    "expert_tech": ArchetypeProfile(
        required_systems=("performance_foundation", "quest_book", "tech", "automation", "recipe_progression", "logistics", "storage_solution", "power_generation", "endgame_goal"),
        recommended_systems=("resource_generation",),
        quality_bar=("Recipes must create a chain, not a pile of machines.", "Quests should explain bottlenecks and automation targets."),
        common_failure_modes=("no recipe changes", "no quest guidance", "tech pile with no chain"),
        default_core_loops=(_loop("Factory Loop", "Automate constrained recipes, unlock better logistics, and scale production toward a final goal.", ["build machines", "automate inputs", "solve bottlenecks"], ["new tiers", "factory scale"]),),
        default_progression_phases=(_phase("Manual Bootstrap", "Give the player enough tools to start automation.", ["tech", "power_generation"], ["first machines"]), _phase("Automation Chain", "Force storage, logistics, and recipe progression to matter.", ["automation", "logistics", "storage_solution", "recipe_progression"], ["tier unlocks"]), _phase("Final Project", "Provide an endgame production or mastery goal.", ["endgame_goal"], ["completion target"])),
    ),
    "tech_automation": ArchetypeProfile(
        required_systems=("performance_foundation", "quest_book", "tech", "automation", "logistics", "storage_solution", "power_generation", "endgame_goal"),
        recommended_systems=("recipe_progression", "resource_generation"),
        quality_bar=("Automation should be useful early and scalable late.", "Storage and logistics must keep pace with machines."),
        common_failure_modes=("tech pile with no chain", "no storage/logistics", "no power pacing"),
        default_core_loops=(_loop("Automation Loop", "Gather resources, build machines, route items, and scale production.", ["mine resources", "automate processing", "expand logistics"], ["efficiency", "new machines"]),),
        default_progression_phases=(_phase("First Machines", "Introduce power and simple automation.", ["tech", "power_generation"], ["machine access"]), _phase("Scaling", "Make storage and logistics central.", ["automation", "logistics", "storage_solution"], ["throughput"])),
    ),
    "magic_progression": ArchetypeProfile(
        required_systems=("performance_foundation", "magic_system", "quest_book", "progression_phases", "gear_upgrade_path"),
        recommended_systems=("atmosphere", "exploration_tools", "boss_progression"),
        quality_bar=("Magic systems need a readable learning path.", "Avoid unrelated spell systems competing for the same fantasy."),
        common_failure_modes=("too many unrelated magic systems", "no clear progression"),
        default_core_loops=(_loop("Arcane Loop", "Study rituals or spells, gather rare components, and unlock stronger magical tools.", ["learn spells", "find components", "perform rituals"], ["new abilities", "gear upgrades"]),),
        default_progression_phases=(_phase("Apprentice", "Give safe early spells and clear costs.", ["magic_system"], ["utility spells"]), _phase("Mastery", "Tie powerful magic to exploration or bosses.", ["gear_upgrade_path", "boss_progression"], ["master spells"])),
    ),
    "skyblock": ArchetypeProfile(
        required_systems=("quest_book", "skyblock_resource_path", "storage_solution", "automation", "resource_generation", "progression_phases"),
        forbidden_or_risky_systems=("overworld_structure_dependency", "normal_worldgen_dependency"),
        quality_bar=("Every essential resource must be obtainable in the void.", "Quests must guide the non-standard resource path."),
        common_failure_modes=("impossible resources", "normal terrain mods that do nothing", "no quest guidance"),
        default_core_loops=(_loop("Island Expansion Loop", "Generate resources from nothing, automate repeat steps, and expand the island.", ["produce resources", "complete quests", "automate generators"], ["new resources", "space"]),),
        default_progression_phases=(_phase("Bootstrap From Nothing", "Establish the first renewable materials.", ["skyblock_resource_path", "resource_generation"], ["basic resources"]), _phase("Automation Island", "Move repetitive generation into machines.", ["automation", "storage_solution"], ["scale"])),
    ),
    "stoneblock": ArchetypeProfile(
        required_systems=("quest_book", "resource_generation", "automation", "storage_solution", "progression_phases", "mining_or_underground_loop"),
        quality_bar=("Mining and compact-base automation must stay central.",),
        common_failure_modes=("no underground identity", "impossible resource chain"),
        default_core_loops=(_loop("Underground Expansion Loop", "Mine, generate resources, automate processing, and carve out better rooms.", ["mine", "process resources", "expand base"], ["automation", "space"]),),
        default_progression_phases=(_phase("Buried Start", "Make mining and resource generation viable.", ["mining_or_underground_loop", "resource_generation"], ["first resources"]),),
    ),
    "horror_survival": ArchetypeProfile(
        required_systems=("performance_foundation", "atmosphere", "soundscape", "horror_mobs", "scarcity", "survival_pressure"),
        recommended_systems=("structures", "limited_exploration_tools"),
        forbidden_or_risky_systems=("overpowered_gear", "full_map_reveal", "too_much_fast_travel"),
        quality_bar=("Fear should come from pacing, vulnerability, and uncertainty.", "Avoid comfort systems that erase threat."),
        common_failure_modes=("annoying instead of scary", "power creep", "enemy spam without pacing"),
        default_core_loops=(_loop("Dread Loop", "Scavenge under pressure, survive the night, and take calculated trips for scarce supplies.", ["scavenge", "hide or fight", "return to shelter"], ["supplies", "survival time"]),),
        default_progression_phases=(_phase("Vulnerable Start", "Establish scarcity and atmosphere before major threats spike.", ["atmosphere", "scarcity"], ["safety"]), _phase("Escalating Threat", "Introduce stronger threats with counterplay.", ["horror_mobs", "survival_pressure"], ["survival mastery"])),
    ),
    "cozy_farming": ArchetypeProfile(
        required_systems=("performance_foundation", "farming", "cooking", "animals", "decoration", "building_blocks"),
        recommended_systems=("villages", "light_exploration", "quest_book"),
        forbidden_or_risky_systems=("hardcore_survival", "horror_mobs", "brutal_combat"),
        quality_bar=("The home, farm, kitchen, and village should all improve over time.", "Danger should not dominate the play session."),
        common_failure_modes=("too much danger", "no collection/decorating goal", "no home/village improvement loop"),
        default_core_loops=(_loop("Homestead Loop", "Grow crops, cook meals, decorate a home, and improve the nearby community.", ["farm", "cook", "decorate", "trade"], ["recipes", "decor", "collection"]),),
        default_progression_phases=(_phase("First Homestead", "Make food, animals, and building options available early.", ["farming", "animals", "building_blocks"], ["home upgrades"]), _phase("Collection Goals", "Add recipes, decorations, or village improvements for replay.", ["cooking", "decoration"], ["collections"])),
    ),
    "exploration_survival": ArchetypeProfile(
        required_systems=("performance_foundation", "worldgen", "structures", "map_tools", "storage_solution", "atmosphere"),
        recommended_systems=("loot_progression", "waypoints_or_fast_travel", "mobs"),
        quality_bar=("Interesting places need rewards and a reason to return home.", "Travel friction should be present but not exhausting."),
        common_failure_modes=("places with no rewards", "too much travel friction", "no reason to return home"),
        default_core_loops=(_loop("Expedition Loop", "Prepare, explore new terrain, loot structures, and return home to upgrade.", ["prepare supplies", "explore", "loot", "return home"], ["discoveries", "base upgrades"]),),
        default_progression_phases=(_phase("Local Survival", "Prepare the player for travel.", ["storage_solution", "map_tools"], ["travel readiness"]), _phase("Long Expeditions", "Reward distant structures and biomes.", ["worldgen", "structures"], ["loot_progression"])),
    ),
    "hardcore_survival": ArchetypeProfile(
        required_systems=("performance_foundation", "survival_pressure", "food_survival", "mobs", "progression_phases"),
        recommended_systems=("scarcity", "atmosphere"),
        forbidden_or_risky_systems=("early overpowered gear", "excessive comfort qol"),
        quality_bar=("Difficulty must create choices, not cheap deaths.",),
        common_failure_modes=("unfair difficulty", "grind with no interesting choices"),
        default_core_loops=(_loop("Pressure Loop", "Balance food, shelter, threat management, and risky resource trips.", ["secure food", "manage threats", "upgrade shelter"], ["survival stability"]),),
        default_progression_phases=(_phase("Fragile Start", "Make basic survival hard but readable.", ["food_survival", "survival_pressure"], ["stability"]),),
    ),
    "building_creative": ArchetypeProfile(
        required_systems=("performance_foundation", "building_blocks", "decoration", "creative_building_tools", "visual_polish"),
        recommended_systems=("worldgen",),
        quality_bar=("Block variety and building workflow matter more than survival pressure.",),
        common_failure_modes=("no block variety", "too much survival friction"),
        default_core_loops=(_loop("Build Loop", "Choose a palette, shape a build, detail it, and iterate visually.", ["collect blocks", "build", "decorate"], ["better palettes", "finished builds"]),),
        default_progression_phases=(_phase("Palette Setup", "Make block and decor choices available.", ["building_blocks", "decoration"], ["palette variety"]),),
    ),
    "multiplayer_smp": ArchetypeProfile(
        required_systems=("performance_foundation", "server_utility", "claims_or_chunk_protection", "multiplayer_social", "client_qol"),
        recommended_systems=("economy", "map_tools"),
        quality_bar=("Server safety, performance, and shared goals beat raw mod count.",),
        common_failure_modes=("grief risk", "too heavy for weaker PCs", "client-only/server mismatch"),
        default_core_loops=(_loop("SMP Loop", "Build near friends, trade or collaborate, protect claims, and keep the server stable.", ["collaborate", "trade", "protect builds"], ["community projects"]),),
        default_progression_phases=(_phase("Server Foundation", "Protect builds and keep common utilities stable.", ["server_utility", "claims_or_chunk_protection"], ["trust"]),),
    ),
    "kitchen_sink": ArchetypeProfile(
        required_systems=("performance_foundation", "quest_book", "storage_solution", "inventory_management", "progression_overview"),
        recommended_systems=("tech", "magic_system", "exploration_tools", "building_blocks"),
        quality_bar=("Breadth needs a map: quests, chapters, or explicit progression overview.", "Remove redundant systems unless variety is the point."),
        common_failure_modes=("bloat", "duplicated systems", "no identity"),
        default_core_loops=(_loop("Sandbox Loop", "Sample major systems, choose a path, and use quests to find long-term goals.", ["try systems", "store loot", "follow chapters"], ["new paths", "mastery goals"]),),
        default_progression_phases=(_phase("Overview", "Explain the main paths before the player drowns in options.", ["progression_overview", "quest_book"], ["direction"]),),
    ),
    "questing_adventure": ArchetypeProfile(
        required_systems=("performance_foundation", "quest_book", "exploration_tools", "progression_overview", "endgame_goal"),
        recommended_systems=("dungeon_progression", "loot_progression", "boss_progression"),
        quality_bar=("Quest chapters should turn exploration into a readable journey.",),
        common_failure_modes=("quest spam", "no final objective"),
        default_core_loops=(_loop("Quest Journey Loop", "Follow chapters, explore places, collect rewards, and unlock the next region or challenge.", ["complete quests", "explore", "upgrade"], ["chapter rewards"]),),
        default_progression_phases=(_phase("Chapter One", "Teach the pack identity quickly.", ["quest_book"], ["direction"]), _phase("Final Chapter", "Point toward an endgame objective.", ["endgame_goal"], ["completion"])),
    ),
    "dark_fantasy": ArchetypeProfile(
        required_systems=("performance_foundation", "atmosphere", "magic_system", "dungeon_progression", "boss_progression", "gear_upgrade_path"),
        recommended_systems=("quest_book", "horror_mobs", "structures"),
        quality_bar=("Threat, magic, and progression should share one dark fantasy tone.",),
        common_failure_modes=("random dark mods", "no progression through danger"),
        default_core_loops=(_loop("Dark Quest Loop", "Survive cursed places, gather occult rewards, and defeat escalating threats.", ["explore ruins", "fight threats", "upgrade gear"], ["dark magic", "boss access"]),),
        default_progression_phases=(_phase("Cursed Start", "Establish tone and basic survival.", ["atmosphere"], ["safety"]), _phase("Forbidden Power", "Tie power gains to dangerous places.", ["magic_system", "boss_progression"], ["mastery"])),
    ),
    "custom": ArchetypeProfile(
        required_systems=("performance_foundation", "core_loop", "progression_phases", "quality_bar"),
        quality_bar=("Define a concrete loop, progression arc, and mod role rules before selecting mods.",),
        common_failure_modes=("vague concept", "no player goal", "random mod pile"),
        default_core_loops=(),
        default_progression_phases=(),
    ),
}


ENDGAME_ARCHETYPES = {"rpg_adventure", "dark_fantasy", "expert_tech", "tech_automation", "kitchen_sink", "questing_adventure", "magic_progression"}

TARGET_MOD_COUNT_RANGES = {
    "vanilla_plus": (25, 70),
    "rpg_adventure": (80, 180),
    "dark_fantasy": (70, 160),
    "expert_tech": (100, 220),
    "tech_automation": (80, 180),
    "magic_progression": (70, 160),
    "skyblock": (70, 180),
    "stoneblock": (70, 180),
    "horror_survival": (45, 120),
    "cozy_farming": (45, 120),
    "exploration_survival": (60, 150),
    "hardcore_survival": (45, 120),
    "building_creative": (40, 130),
    "multiplayer_smp": (40, 120),
    "kitchen_sink": (150, 300),
    "questing_adventure": (80, 180),
    "custom": (50, 150),
}


def infer_pack_design_from_concept(
    concept_text: str,
    *,
    name: str | None = None,
    minecraft_version: str = "1.20.1",
    loader: Loader = "fabric",
) -> PackDesign:
    concept = " ".join(concept_text.split())
    lower = concept.lower()
    archetype = _infer_archetype(lower)
    profile = ARCHETYPE_PROFILES[archetype]
    pack_name = name or _name_from_concept(concept)
    pillars = [
        PackDesignPillar(
            name=system.replace("_", " ").title(),
            priority="core" if system in profile.required_systems else "supporting",
            required_capabilities=[system],
        )
        for system in profile.required_systems[:6]
        if system not in {"core_loop", "progression_phases", "quality_bar"}
    ]
    required_systems = list(profile.required_systems)
    required_systems.extend(_explicit_system_hints(lower, archetype))
    if archetype != "custom" and "performance_foundation" not in required_systems:
        required_systems.insert(0, "performance_foundation")
    quality_bar = list(profile.quality_bar) or [f"Make the {archetype.replace('_', ' ')} loop clear, paced, and coherent."]
    forbidden = list(profile.forbidden_or_risky_systems)
    if archetype == "vanilla_plus":
        forbidden.extend(["large_magic_progression", "too_many_content_systems"])
    if archetype == "cozy_farming":
        forbidden.extend(["horror_mobs", "hardcore_survival", "brutal_combat"])
    required_systems = _unique_strings(required_systems)
    forbidden = _unique_strings(forbidden)
    return PackDesign(
        name=pack_name,
        summary=concept or f"A {archetype.replace('_', ' ')} Minecraft modpack.",
        minecraft_version=minecraft_version,
        loader=loader,
        archetype=archetype,
        intended_session_style=_session_style_for(archetype),
        difficulty_target=_difficulty_for(archetype),
        pillars=pillars,
        core_loops=list(profile.default_core_loops),
        progression_phases=list(profile.default_progression_phases),
        required_systems=required_systems,
        forbidden_systems=forbidden,
        soft_allowed_systems=list(profile.recommended_systems),
        must_have_experience_beats=_experience_beats_for(archetype),
        optional_experience_beats=list(profile.common_failure_modes),
        mod_selection_rules=_mod_rules_for(archetype),
        config_or_datapack_needs=_config_needs_for(archetype),
        quality_bar=quality_bar,
    )


def review_pack_design(design: PackDesign) -> PackDesignReviewReport:
    issues: list[PackDesignReviewIssue] = []
    missing: list[str] = []

    def add(severity: str, category: str, title: str, detail: str, action: str) -> None:
        issues.append(PackDesignReviewIssue(severity=severity, category=category, title=title, detail=detail, suggested_action=action))

    if not design.summary or _is_vague_text(design.summary):
        add("high", "theme_clarity", "Design summary is vague", "The summary needs concrete player activities and goals.", "Rewrite the summary around a player loop.")
        missing.append("concrete summary")
    if not design.pillars:
        add("high", "theme_clarity", "Missing design pillars", "The pack has no explicit pillars to discipline mod roles.", "Add 3-6 pillars with core/supporting priorities.")
        missing.append("pillars")
    if not design.core_loops:
        add("high", "core_gameplay_loop", "Missing core loop", "Players need a repeated action and reward cycle.", "Add at least one GameplayLoop.")
        missing.append("core loop")
    if not design.progression_phases:
        add("high", "progression_arc", "Missing progression phases", "The design does not explain how play changes over time.", "Add early, mid, and late phase expectations where relevant.")
        missing.append("progression phases")
    if not design.required_systems:
        add("high", "system_requirements", "Missing required systems", "The reviewer cannot judge mod coverage without required systems.", "List the systems every selected list must cover.")
        missing.append("required systems")
    if not design.quality_bar:
        add("high", "quality_bar", "Missing quality bar", "The pack has no standard for what good looks like.", "Add concrete quality checks for cohesion, pacing, and fun.")
        missing.append("quality bar")
    overlap = sorted(set(design.required_systems) & set(design.forbidden_systems))
    if overlap:
        add("critical", "contradiction", "Required systems are also forbidden", ", ".join(overlap), "Remove the contradiction before selecting mods.")
    if design.archetype in ENDGAME_ARCHETYPES and not _design_mentions_endgame(design):
        add("warning", "endgame_goal", "Missing endgame or replay goal", "This archetype benefits from a visible long-term objective.", "Add a boss, final recipe, mastery, collection, or replay goal.")
        missing.append("endgame or replay goal")
    for loop in design.core_loops:
        if _is_vague_text(loop.description) and not loop.repeated_player_actions:
            add("warning", "core_gameplay_loop", f"Vague loop: {loop.name}", "Loop text does not name concrete actions.", "Add repeated actions and reward types.")

    score = _score_from_design_issues(issues)
    severities = {issue.severity for issue in issues}
    if score >= 80 and not (severities & {"high", "critical"}):
        readiness = "ready_for_mod_selection"
        status = "passed"
        verdict = "Design is ready for deterministic mod selection."
    elif score >= 55 and "critical" not in severities:
        readiness = "revise_design_first"
        status = "warnings"
        verdict = "Design has a useful direction, but revise weak areas before selecting mods."
    else:
        readiness = "not_enough_direction"
        status = "failed"
        verdict = "Design needs more concrete direction before mod selection."
    return PackDesignReviewReport(
        run_id=_stable_run_id(design.model_dump_json()),
        status=status,
        score=score,
        verdict=verdict,
        readiness=readiness,
        design=design,
        issues=issues,
        missing_design_elements=list(dict.fromkeys(missing)),
        recommended_next_actions=_design_next_actions(readiness),
    )


def generate_pack_blueprint(design: PackDesign) -> PackBlueprint:
    profile = ARCHETYPE_PROFILES.get(design.archetype, ARCHETYPE_PROFILES["custom"])
    target_min, target_max = TARGET_MOD_COUNT_RANGES.get(design.archetype, TARGET_MOD_COUNT_RANGES["custom"])
    required_systems = _blueprint_required_systems(design)
    recommended_systems = _blueprint_recommended_systems(design, profile)
    forbidden_systems = _blueprint_forbidden_systems(design, profile)

    required_slots = [
        _blueprint_slot(design, system, "required", slot_index=index)
        for index, system in enumerate(required_systems, start=1)
        if system not in {"core_loop", "quality_bar", "progression_phases"}
    ]
    recommended_slots = [
        _blueprint_slot(design, system, "recommended", slot_index=index)
        for index, system in enumerate(recommended_systems, start=1)
        if system not in set(required_systems)
    ]
    optional_slots = _optional_blueprint_slots(design, set(required_systems) | set(recommended_systems))
    forbidden_slots = [
        _blueprint_slot(design, system, "forbidden", slot_index=index)
        for index, system in enumerate(forbidden_systems, start=1)
    ]

    return PackBlueprint(
        name=design.name,
        minecraft_version=design.minecraft_version,
        loader=design.loader,
        archetype=design.archetype,
        summary=design.summary,
        target_mod_count_min=target_min,
        target_mod_count_max=target_max,
        required_slots=required_slots,
        recommended_slots=recommended_slots,
        optional_slots=optional_slots,
        forbidden_slots=forbidden_slots,
        compatibility_cautions=_blueprint_cautions(design, forbidden_systems),
        config_or_datapack_expectations=_blueprint_config_expectations(design),
        quest_expectations=_blueprint_quest_expectations(design),
        quality_bar=list(design.quality_bar or profile.quality_bar),
    )


def _blueprint_required_systems(design: PackDesign) -> list[str]:
    systems = list(design.required_systems)
    if design.archetype == "horror_survival":
        systems = [system for system in systems if system not in {"map_tools", "full_map_reveal", "too_much_fast_travel"}]
    if design.archetype == "expert_tech":
        systems.extend(["quest_book", "automation", "recipe_progression", "power_generation", "logistics", "storage_solution"])
    if design.archetype == "skyblock":
        systems.extend(["skyblock_resource_path", "resource_generation"])
    if design.archetype == "cozy_farming":
        systems.extend(["farming", "cooking", "animals", "decoration"])
    return _unique_strings(systems)


def _blueprint_recommended_systems(design: PackDesign, profile: ArchetypeProfile) -> list[str]:
    systems = list(design.soft_allowed_systems) + list(profile.recommended_systems)
    if design.archetype == "horror_survival":
        systems = [system for system in systems if system not in {"map_tools", "waypoints_or_fast_travel"}]
        systems.extend(["limited_exploration_tools"])
    if design.archetype == "cozy_farming":
        systems.extend(["villages", "building_blocks"])
    return _unique_strings(systems)


def _blueprint_forbidden_systems(design: PackDesign, profile: ArchetypeProfile) -> list[str]:
    systems = list(design.forbidden_systems) + list(profile.forbidden_or_risky_systems)
    if design.archetype == "horror_survival":
        systems.extend(["full_map_reveal", "too_much_fast_travel", "overpowered_gear"])
    if design.archetype == "cozy_farming":
        systems.extend(["horror_mobs", "hardcore_survival"])
    if design.archetype == "skyblock":
        systems.extend(["normal_worldgen_dependency", "overworld_structure_dependency"])
    return _unique_strings(systems)


def _optional_blueprint_slots(design: PackDesign, already_used: set[str]) -> list[ModBlueprintSlot]:
    optional_systems: list[str] = []
    if design.archetype == "horror_survival":
        optional_systems.append("map_tools")
    elif design.archetype == "vanilla_plus":
        optional_systems.extend(["visual_polish", "decoration"])
    elif design.archetype == "cozy_farming":
        optional_systems.extend(["light_exploration", "quest_book"])
    return [
        _blueprint_slot(design, system, "optional", slot_index=index)
        for index, system in enumerate(_unique_strings(optional_systems), start=1)
        if system not in already_used
    ]


def _blueprint_slot(design: PackDesign, system: str, priority: str, *, slot_index: int) -> ModBlueprintSlot:
    min_count, max_count = _slot_count_range(system, priority, design.archetype)
    if priority == "forbidden":
        min_count, max_count = 0, 0
    return ModBlueprintSlot(
        slot_id=f"{priority}_{slot_index:02d}_{_slot_id_slug(system)}",
        system_tag=system,
        priority=priority,
        purpose=_slot_purpose(system, design.archetype, priority),
        min_count=min_count,
        max_count=max_count,
        search_terms=[] if priority == "forbidden" else _slot_search_terms(system, design),
        selection_rules=_slot_selection_rules(system, design, priority),
        avoid_rules=_slot_avoid_rules(system, design, priority),
        supports_phases=_supporting_phases(system, design),
        supports_loops=[loop.name for loop in design.core_loops if _loop_supports_system(loop, system)] or [loop.name for loop in design.core_loops[:1]],
    )


def _slot_count_range(system: str, priority: str, archetype: str) -> tuple[int, int]:
    if system == "performance_foundation":
        return 3, 8
    if system == "quest_book":
        return 1, 1
    if system == "storage_solution":
        return 1, 3
    if system in {"recipe_progression", "power_generation", "logistics", "skyblock_resource_path", "resource_generation"}:
        return 1, 3
    if system in {"farming", "cooking", "animals", "decoration", "building_blocks"}:
        return (1, 4) if archetype == "cozy_farming" else (0 if priority == "optional" else 1, 3)
    if system in {"worldgen", "structures", "dungeon_progression", "boss_progression", "magic_system", "tech", "automation"}:
        return 1, 4
    if priority == "recommended":
        return 0, 2
    if priority == "optional":
        return 0, 1
    return 1, 2


def _slot_search_terms(system: str, design: PackDesign) -> list[str]:
    loader = design.loader
    version = design.minecraft_version
    specific = {
        "performance_foundation": [
            f"{loader} {version} performance Sodium Lithium FerriteCore",
            f"{loader} {version} optimization EntityCulling ImmediatelyFast ModernFix",
        ],
        "quest_book": [f"{loader} {version} quest book FTB Quests"],
        "storage_solution": [f"{loader} {version} storage backpacks inventory management"],
        "inventory_management": [f"{loader} {version} inventory management EMI REI JEI mouse tweaks"],
        "client_qol": [f"{loader} {version} client quality of life Jade AppleSkin Mod Menu"],
        "automation": [f"{loader} {version} automation factory Create machines"],
        "recipe_progression": [f"{loader} {version} recipe progression KubeJS CraftTweaker expert"],
        "power_generation": [f"{loader} {version} power generation energy machines tech"],
        "logistics": [f"{loader} {version} logistics pipes cables item transport"],
        "skyblock_resource_path": [f"{loader} {version} skyblock resource path ex nihilo sieves cobblegen"],
        "resource_generation": [f"{loader} {version} resource generation generators sieves"],
        "farming": [f"{loader} {version} farming crops Croptopia Farmer's Delight"],
        "cooking": [f"{loader} {version} cooking food meals Farmer's Delight"],
        "animals": [f"{loader} {version} animals livestock wildlife cozy"],
        "decoration": [f"{loader} {version} decoration furniture Macaw Supplementaries"],
        "villages": [f"{loader} {version} villages villagers towns cozy"],
        "horror_mobs": [f"{loader} {version} horror mobs darkness scary survival"],
        "soundscape": [f"{loader} {version} ambient sounds soundscape footsteps horror"],
        "atmosphere": [f"{loader} {version} atmosphere ambience fog visual survival"],
        "scarcity": [f"{loader} {version} scarcity survival loot resources"],
        "survival_pressure": [f"{loader} {version} survival pressure thirst temperature darkness"],
        "worldgen": [f"{loader} {version} worldgen biomes terrain exploration"],
        "structures": [f"{loader} {version} structures dungeons ruins towers"],
        "dungeon_progression": [f"{loader} {version} dungeons progression adventure structures"],
        "boss_progression": [f"{loader} {version} bosses progression endgame adventure"],
        "loot_progression": [f"{loader} {version} loot progression treasure artifacts"],
        "gear_upgrade_path": [f"{loader} {version} gear upgrade weapons armor progression"],
        "map_tools": [f"{loader} {version} map minimap atlas exploration"],
        "limited_exploration_tools": [f"{loader} {version} limited exploration compass atlas no full map reveal"],
        "building_blocks": [f"{loader} {version} building blocks Chipped Rechiseled palettes"],
    }
    return specific.get(system, [f"{loader} {version} {design.archetype.replace('_', ' ')} {system.replace('_', ' ')}"])


def _slot_selection_rules(system: str, design: PackDesign, priority: str) -> list[str]:
    rules = [f"Select mods that clearly provide {system.replace('_', ' ')} for a {design.archetype.replace('_', ' ')} pack."]
    if priority == "required":
        rules.append("This slot must be covered before optional flavor mods.")
    if system == "performance_foundation":
        rules.append("Prefer a small compatible foundation stack over experimental overlap.")
    if system == "quest_book":
        rules.append("Use the quest system to explain the core loop and progression phases.")
    if design.archetype == "expert_tech" and system in {"automation", "recipe_progression", "power_generation", "logistics", "storage_solution"}:
        rules.append("This slot should support a readable gated automation chain.")
    return rules


def _slot_avoid_rules(system: str, design: PackDesign, priority: str) -> list[str]:
    if priority == "forbidden":
        return [f"Do not include mods whose primary role is {system.replace('_', ' ')}."]
    rules = [f"Avoid mods that violate forbidden systems: {', '.join(design.forbidden_systems) or 'none'}."]
    specific = {
        "performance_foundation": "Do not include incompatible renderer replacements together.",
        "quest_book": "Do not include multiple quest book systems unless the design explicitly requires migration.",
        "storage_solution": "Avoid late-game-only storage as the only storage solution.",
        "map_tools": "Avoid full map reveal when the pack depends on mystery, horror, or limited navigation.",
        "limited_exploration_tools": "Avoid full map reveal and too much fast travel.",
        "tech": "Avoid tech systems in packs that do not explicitly ask for tech.",
        "automation": "Avoid automation systems that erase the intended survival or cozy loop.",
        "horror_mobs": "Avoid horror systems unless the design calls for horror.",
        "hardcore_survival": "Avoid hardcore survival pressure unless the design calls for it.",
    }
    if system in specific:
        rules.append(specific[system])
    if design.archetype == "vanilla_plus":
        rules.append("Avoid heavy content systems that make the pack stop feeling vanilla+.")
    if design.archetype == "horror_survival":
        rules.append("Avoid full_map_reveal, too_much_fast_travel, and overpowered_gear.")
    if design.archetype == "cozy_farming":
        rules.append("Avoid horror_mobs and hardcore_survival systems.")
    if design.archetype == "skyblock":
        rules.append("Avoid normal overworld worldgen or structure dependencies unless explicitly void-compatible.")
    return rules


def _slot_purpose(system: str, archetype: str, priority: str) -> str:
    if priority == "forbidden":
        return f"Keep {system.replace('_', ' ')} out of the pack so the {archetype.replace('_', ' ')} experience stays coherent."
    purposes = {
        "performance_foundation": "Keep the pack playable and smooth before adding content.",
        "quest_book": "Give players a readable route through the gameplay loop and progression.",
        "storage_solution": "Prevent inventory friction from blocking progression.",
        "automation": "Let players convert repeated work into scalable systems.",
        "recipe_progression": "Create deterministic gates and meaningful production goals.",
        "skyblock_resource_path": "Ensure essential resources are obtainable without normal terrain.",
        "resource_generation": "Provide renewable materials that support non-standard worlds.",
        "farming": "Anchor the home and food loop.",
        "cooking": "Turn farming into meaningful meals and collection goals.",
        "animals": "Support cozy homestead life and gentle progression.",
        "decoration": "Reward home improvement and visual identity.",
        "horror_mobs": "Create threat pressure that supports horror pacing.",
        "atmosphere": "Make the theme legible moment to moment.",
    }
    return purposes.get(system, f"Support the {archetype.replace('_', ' ')} design through {system.replace('_', ' ')}.")


def _supporting_phases(system: str, design: PackDesign) -> list[str]:
    matches = [
        phase.name
        for phase in design.progression_phases
        if system in phase.required_systems or any(_system_alias_match(system, required) for required in phase.required_systems)
    ]
    return matches or [phase.name for phase in design.progression_phases[:1]]


def _loop_supports_system(loop: GameplayLoop, system: str) -> bool:
    text = " ".join([loop.name, loop.description, *loop.repeated_player_actions, *loop.reward_types]).lower()
    return any(term in text for term in system.replace("_", " ").split())


def _system_alias_match(system: str, required: str) -> bool:
    aliases = {
        "limited_exploration_tools": {"map_tools", "exploration_tools"},
        "light_exploration": {"map_tools", "structures", "exploration_tools"},
        "progression_phases": {"quest_book", "recipe_progression", "boss_progression"},
    }
    return required in aliases.get(system, set()) or system in aliases.get(required, set())


def _blueprint_cautions(design: PackDesign, forbidden_systems: list[str]) -> list[str]:
    cautions = [
        "Verify real Modrinth project/version/file metadata before selecting mods.",
        "Do not use guessed download URLs or unverified versions.",
        "Prefer coherent coverage over filling every optional slot.",
    ]
    if forbidden_systems:
        cautions.append("Respect forbidden systems: " + ", ".join(forbidden_systems) + ".")
    if design.archetype == "skyblock":
        cautions.append("Avoid normal overworld worldgen or structure dependency unless the mod is explicitly skyblock/void compatible.")
    if design.archetype == "horror_survival":
        cautions.append("Avoid full map reveal, too much fast travel, and overpowered gear because they flatten horror pacing.")
    if design.archetype == "cozy_farming":
        cautions.append("Avoid horror or hardcore survival pressure that competes with the farm/home loop.")
    return cautions


def _blueprint_config_expectations(design: PackDesign) -> list[str]:
    expectations = list(design.config_or_datapack_needs)
    if design.archetype == "expert_tech":
        expectations.append("Recipe gating or datapack/KubeJS-style changes should define the expert progression chain.")
    if design.archetype == "skyblock":
        expectations.append("Resource recipes and quest rewards must make every required material obtainable in the void.")
    return _unique_strings(expectations)


def _blueprint_quest_expectations(design: PackDesign) -> list[str]:
    if "quest_book" not in design.required_systems and "quest_book" not in design.soft_allowed_systems:
        return []
    expectations = ["Quest chapters should explain the core gameplay loop, required systems, and progression milestones."]
    expectations.extend(f"Include phase guidance for {phase.name}: {phase.purpose}" for phase in design.progression_phases)
    return expectations


def _slot_id_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "slot"


def _unique_strings(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value.strip().lower() for value in values if value and value.strip()))


KNOWN_MOD_SYSTEM_TAGS = {
    "ct-overhaul-village": {"villages", "structures", "light_exploration"},
    "choicetheorems-overhauled-village": {"villages", "structures", "light_exploration"},
    "ctov": {"villages", "structures", "light_exploration"},
    "naturalist": {"animals", "mobs", "atmosphere"},
    "terralith": {"worldgen", "biome_discovery"},
    "regions-unexplored": {"worldgen", "biome_discovery"},
    "explorify": {"structures", "light_exploration", "exploration_tools"},
    "farmers-delight-refabricated": {"farming", "cooking", "food_survival"},
    "farmers-delight": {"farming", "cooking", "food_survival"},
    "croptopia": {"farming", "cooking"},
    "croptopia-delight": {"farming", "cooking"},
    "chipped": {"building_blocks", "decoration"},
    "rechiseled": {"building_blocks", "decoration"},
    "supplementaries": {"building_blocks", "decoration", "client_qol"},
    "another-furniture": {"decoration", "building_blocks"},
    "handcrafted": {"decoration", "building_blocks"},
    "toms-storage": {"base_storage", "storage_solution"},
    "simple-storage-network": {"base_storage", "storage_solution"},
    "storage-drawers": {"base_storage", "storage_solution"},
    "travelersbackpack": {"mobile_storage", "storage_solution", "exploration_tools"},
    "traveler-s-backpack": {"mobile_storage", "storage_solution", "exploration_tools"},
    "xaeros-minimap": {"minimap", "map_tools", "exploration_tools"},
    "xaeros-world-map": {"world_map", "map_tools", "exploration_tools"},
    "journeymap": {"minimap", "world_map", "map_tools", "full_map_reveal"},
    "voxelmap": {"minimap", "map_tools", "full_map_reveal"},
    "antique-atlas": {"world_map", "map_tools", "light_exploration"},
    "waystones": {"waypoints_or_fast_travel", "exploration_tools"},
    "visuality": {"visual_polish", "atmosphere"},
    "ambientsounds": {"soundscape", "atmosphere"},
    "sound-physics-remastered": {"soundscape", "atmosphere"},
    "sodium": {"performance_foundation"},
    "lithium": {"performance_foundation"},
    "ferrite-core": {"performance_foundation"},
    "ferritecore": {"performance_foundation"},
    "modernfix": {"performance_foundation"},
    "immediatelyfast": {"performance_foundation"},
    "entityculling": {"performance_foundation"},
    "modmenu": {"client_qol"},
    "jade": {"client_qol"},
    "emi": {"client_qol", "inventory_qol", "inventory_management"},
    "rei": {"client_qol", "inventory_qol", "inventory_management"},
    "appleskin": {"client_qol", "food_survival"},
    "mouse-tweaks": {"client_qol", "inventory_qol", "inventory_management"},
    "shulkerboxtooltip": {"client_qol", "inventory_qol", "inventory_management"},
    "inventory-profiles-next": {"client_qol", "inventory_qol", "inventory_management"},
}

LARGE_WORLDGEN_OVERHAULS = {
    "terralith",
    "regions-unexplored",
    "biomes-o-plenty",
    "oh-the-biomes-weve-gone",
    "tectonic",
    "amplified-nether",
}


def _normalize_mod_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")


def _known_keys_for(candidate: CandidateMod) -> set[str]:
    return {
        key
        for value in (candidate.slug, candidate.project_id, candidate.title)
        for key in {_normalize_mod_key(value), _normalize_mod_key(value).replace("-", "")}
        if key
    }


def is_large_worldgen_overhaul(candidate: CandidateMod, tags: set[str] | None = None) -> bool:
    keys = _known_keys_for(candidate)
    if keys & LARGE_WORLDGEN_OVERHAULS:
        return True
    if keys & {"ct-overhaul-village", "choicetheorems-overhauled-village", "ctov", "naturalist", "explorify"}:
        return False
    tags = tags or infer_mod_system_tags(candidate)
    if "worldgen" not in tags:
        return False
    text = _candidate_text(candidate)
    positive = ("terrain", "biome", "biomes", "worldgen", "world generation", "overworld", "nether terrain")
    negative = ("village", "structure", "dungeon", "tower", "animal", "wildlife", "mob")
    return any(term in text for term in positive) and not any(term in text for term in negative)


def infer_mod_system_tags(candidate: CandidateMod) -> set[str]:
    text = _candidate_text(candidate)
    tags: set[str] = set()
    known_tags: set[str] = set()
    for key in _known_keys_for(candidate):
        known_tags.update(KNOWN_MOD_SYSTEM_TAGS.get(key, set()))
    if known_tags:
        tags.update(known_tags)
        if "worldgen" in tags:
            tags.add("normal_worldgen_dependency")
        if "structures" in tags:
            tags.add("overworld_structure_dependency")
            tags.add("biome_discovery")
            tags.add("exploration_tools")
        return tags
    capabilities = set(candidate.matched_capabilities or [])
    if capabilities & {"renderer_optimization", "logic_optimization", "memory_optimization", "entity_culling", "performance_foundation"}:
        tags.add("performance_foundation")
    rules: list[tuple[str, Iterable[str]]] = [
        ("performance_foundation", ("sodium", "lithium", "ferritecore", "ferrite-core", "immediatelyfast", "modernfix", "krypton", "entityculling", "entity culling", "starlight", "c2me", "optimization", "performance")),
        ("quest_book", ("ftb-quests", "ftb quests", "questbook", "quest book", "better-questing", "quests")),
        ("map_tools", ("xaero", "journeymap", "voxelmap", "antique-atlas", "atlas", "minimap", "world map")),
        ("full_map_reveal", ("journeymap", "world map", "xaeros-world-map", "voxelmap")),
        ("waypoints_or_fast_travel", ("waystones", "teleport", "warp", "waypoint", "fast travel")),
        ("storage_solution", ("backpack", "travelers-backpack", "storage-drawers", "toms-storage", "tom's simple storage", "simple-storage", "ae2", "applied energistics", "refined-storage", "chest")),
        ("inventory_management", ("inventory", "mouse tweaks", "jei", "emi", "rei", "roughly enough items", "jade", "wthit")),
        ("client_qol", ("modmenu", "jade", "appleskin", "mouse tweaks", "inventory", "utility", "qol", "emi", "rei", "jei")),
        ("tech", ("create", "mekanism", "thermal expansion", "industrialcraft", "tech reborn", "ad astra", "machine", "factory")),
        ("automation", ("create", "automate", "conveyor", "mechanical", "refined storage", "applied energistics")),
        ("power_generation", ("power", "energy", "generator", "mekanism", "thermal", "industrial")),
        ("logistics", ("cable", "pipe", "logistic", "drawer", "tunnel", "router", "transport")),
        ("recipe_progression", ("expert", "greg", "kubejs", "crafttweaker", "hard recipe", "recipe progression", "extended crafting")),
        ("magic_system", ("ars-nouveau", "botania", "hexcasting", "occultism", "spectrum", "spell", "mana")),
        ("skill_tree", ("skill tree", "skills", "leveling", "levelz", "puffish")),
        ("class_system", ("class", "origins", "rpg classes")),
        ("farming", ("farmers-delight", "croptopia", "farming", "crop", "farm", "harvest")),
        ("cooking", ("farmers-delight", "cooking", "food", "meal", "kitchen")),
        ("food_survival", ("food", "nutrition", "hunger", "spice of life")),
        ("animals", ("animal", "critters", "livestock", "naturalist")),
        ("villages", ("village", "villager", "town")),
        ("building_blocks", ("chipped", "rechiseled", "block", "builder", "palette")),
        ("decoration", ("supplementaries", "macaw", "furniture", "decoration", "decor", "chipped", "rechiseled")),
        ("creative_building_tools", ("worldedit", "axiom", "litematica", "creative", "building tools")),
        ("visual_polish", ("visual", "particles", "iris", "shader", "continuity")),
        ("atmosphere", ("atmosphere", "ambient", "ambience", "darkness", "fog", "visuality", "sound")),
        ("soundscape", ("sound", "ambience", "ambient", "presence footsteps", "soundscape")),
        ("horror_mobs", ("horror", "parasite", "infection", "from the fog", "sanity", "scary")),
        ("scarcity", ("scarcity", "scarce", "limited resources", "hardcore")),
        ("survival_pressure", ("thirst", "temperature", "tough-as-nails", "dehydration", "cold", "heat")),
        ("hardcore_survival", ("hardcore", "tough-as-nails", "tough as nails", "first aid", "realistic survival")),
        ("temperature_thirst_or_survival", ("temperature", "thirst", "tough-as-nails", "dehydration")),
        ("worldgen", ("terralith", "tectonic", "biomes", "worldgen", "terrain", "regions unexplored")),
        ("normal_worldgen_dependency", ("terralith", "tectonic", "biomes", "worldgen", "terrain", "regions unexplored")),
        ("structures", ("dungeon", "yung", "tower", "structure", "ruins", "when dungeons arise", "village")),
        ("overworld_structure_dependency", ("dungeon", "tower", "structure", "ruins", "when dungeons arise", "village")),
        ("dungeon_progression", ("dungeon", "when dungeons arise", "tower", "roguelike")),
        ("boss_progression", ("boss", "adventurez", "bosses-of-mass-destruction", "cataclysm")),
        ("loot_progression", ("loot", "treasure", "artifacts", "relics")),
        ("gear_upgrade_path", ("gear", "weapon", "armor", "equipment", "simply swords", "tier")),
        ("mobs", ("mobs", "creatures", "monsters", "hostile")),
        ("dimensions", ("dimension", "nether", "end", "twilight")),
        ("exploration_tools", ("compass", "map", "waystone", "exploration", "atlas")),
        ("biome_discovery", ("biome", "exploration", "nature")),
        ("resource_generation", ("resource generation", "cobblegen", "generator", "sieve", "ex nihilo", "ex-nihilo")),
        ("skyblock_resource_path", ("skyblock", "sieve", "sieves", "ex nihilo", "ex-nihilo", "cobblegen", "void")),
        ("server_utility", ("server", "spark", "ledger", "chunky", "ban", "luckperms")),
        ("multiplayer_social", ("smp", "multiplayer", "friends", "social", "voice chat")),
        ("economy", ("economy", "shop", "trading")),
        ("claims_or_chunk_protection", ("claim", "chunk protection", "ftb chunks", "open parties and claims")),
        ("developer_or_debug_only", ("debug", "developer", "probejs")),
        ("novelty_or_meme", ("meme", "joke", "funny", "disc", "chicken")),
        ("endgame_goal", ("endgame", "final", "creative item", "avaritia", "ultimate", "mastery")),
        ("overpowered_gear", ("avaritia", "overpowered", "creative item", "infinity armor", "god gear")),
    ]
    for tag, terms in rules:
        if any(term in text for term in terms):
            tags.add(tag)
    if "worldgen" in tags or "structures" in tags:
        tags.add("biome_discovery")
    if "dungeon_progression" in tags or "structures" in tags:
        tags.add("exploration_tools")
    return tags


def review_selected_mods_against_design(
    selected: SelectedModList,
    candidates: list[CandidateMod],
    design: PackDesign,
) -> tuple[
    dict[str, list[str]],
    list[str],
    list[str],
    list[ReviewIssue],
    list[ReviewIssue],
    list[ReviewIssue],
    list[ReviewIssue],
    list[ReviewIssue],
    int,
]:
    tags_by_slug = {candidate.slug: infer_mod_system_tags(candidate) for candidate in candidates}
    coverage: dict[str, list[str]] = {}
    for candidate in candidates:
        for tag in sorted(tags_by_slug[candidate.slug]):
            coverage.setdefault(tag, []).append(candidate.slug)

    required = [system for system in design.required_systems if system not in {"core_loop", "quality_bar"}]
    missing = [system for system in required if not _system_covered(system, coverage, design)]
    weak = [system for system in required if system in coverage and len(coverage[system]) == 1 and system not in {"performance_foundation"}]
    if design.archetype == "cozy_farming":
        weak = []
    anti_goal_violations = _anti_goal_issues(design, coverage)
    progression_gaps = _progression_gap_issues(design, coverage, missing)
    cohesion_issues = _cohesion_issues(selected, candidates, design, coverage, tags_by_slug)
    pacing_issues = _pacing_issues(design, coverage)
    config_warnings = _config_warnings(design, coverage)

    issues = anti_goal_violations + progression_gaps + cohesion_issues + pacing_issues + config_warnings
    score = 100
    score -= len(missing) * 10
    score -= len(weak) * 4
    for issue in issues:
        score -= {"critical": 30, "high": 15, "warning": 6, "info": 0}[issue.severity]
    if "performance_foundation" in design.required_systems and "performance_foundation" in missing:
        score -= 10
    return (
        {key: sorted(dict.fromkeys(value)) for key, value in sorted(coverage.items())},
        missing,
        weak,
        anti_goal_violations,
        progression_gaps,
        cohesion_issues,
        pacing_issues,
        config_warnings,
        max(0, min(100, score)),
    )


def _infer_archetype(text: str) -> str:
    checks = [
        ("skyblock", ("skyblock", "island", "void")),
        ("stoneblock", ("stoneblock", "underground block world")),
        ("horror_survival", ("horror", "scary", "parasite", "darkness")),
        ("cozy_farming", ("cozy", "farming", "stardew", "peaceful")),
        ("expert_tech", ("expert", "greg", "hard recipes", "automation chain")),
        ("tech_automation", ("tech", "factory", "automation")),
        ("magic_progression", ("magic", "spells", "rituals")),
        ("hardcore_survival", ("hardcore", "realistic survival", "thirst", "temperature")),
        ("building_creative", ("building", "creative", "decorating")),
        ("multiplayer_smp", ("server", "smp", "friends", "multiplayer")),
        ("rpg_adventure", ("rpg", "bosses", "dungeons", "classes")),
        ("vanilla_plus", ("vanilla plus", "vanilla+", "enhanced vanilla")),
        ("exploration_survival", ("exploration", "survival", "worldgen", "structures")),
    ]
    for archetype, terms in checks:
        if any(_contains_term(text, term) for term in terms):
            return archetype
    return "custom"


def _contains_term(text: str, term: str) -> bool:
    normalized = term.strip().lower()
    if not normalized:
        return False
    pattern = r"\b" + re.escape(normalized).replace(r"\ ", r"\s+") + r"\b"
    for match in re.finditer(pattern, text):
        left_context = text[max(0, match.start() - 24) : match.start()]
        if re.search(r"(no|not|without|avoid|avoids|avoiding)\s+$", left_context):
            continue
        return True
    return False


def _explicit_system_hints(text: str, archetype: str) -> list[str]:
    if archetype != "cozy_farming":
        return []
    cozy_system_terms = (
        "worldgen",
        "villages",
        "light_exploration",
        "storage_solution",
        "inventory_management",
        "client_qol",
        "visual_polish",
        "atmosphere",
        "building_blocks",
        "decoration",
        "farming",
        "cooking",
        "animals",
    )
    return [system for system in cozy_system_terms if _contains_term(text, system)]


def _name_from_concept(concept: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", concept)[:5]
    return " ".join(words).title() or "MythWeaver Pack"


def _session_style_for(archetype: str) -> str:
    return {
        "multiplayer_smp": "server_multiplayer",
        "building_creative": "creative_building",
        "hardcore_survival": "challenge_run",
        "expert_tech": "long_sessions",
        "tech_automation": "long_sessions",
        "cozy_farming": "short_sessions",
    }.get(archetype, "mixed")


def _difficulty_for(archetype: str) -> str:
    return {
        "expert_tech": "expert",
        "hardcore_survival": "hardcore",
        "horror_survival": "challenging",
        "cozy_farming": "relaxed",
        "building_creative": "relaxed",
    }.get(archetype, "normal")


def _experience_beats_for(archetype: str) -> list[str]:
    return {
        "expert_tech": ["first automated line", "stable storage/logistics", "final recipe or factory goal"],
        "horror_survival": ["unsafe first night", "meaningful shelter", "escalating but paced threats"],
        "cozy_farming": ["first harvest", "signature meal", "decorated home or village improvement"],
        "skyblock": ["first renewable resource", "automated resource generation", "expanded island milestone"],
    }.get(archetype, ["clear early goal", "midgame change in capability", "replay or completion target"])


def _mod_rules_for(archetype: str) -> list[str]:
    rules = ["Every selected mod should serve a named system or design pillar.", "Prefer maintained Modrinth projects.", "Prioritize coherence over mod count."]
    if archetype == "vanilla_plus":
        rules.append("Reject heavy content systems that make the pack stop feeling vanilla+.")
    if archetype == "cozy_farming":
        rules.append("Avoid horror, hardcore survival, and brutal combat pressure.")
    if archetype == "horror_survival":
        rules.append("Avoid comfort systems that reveal all danger or trivialize travel.")
    if archetype in {"expert_tech", "tech_automation"}:
        rules.append("Require storage, logistics, power, and automation to form a readable chain.")
    return rules


def _config_needs_for(archetype: str) -> list[str]:
    if archetype in {"expert_tech", "skyblock", "stoneblock"}:
        return ["Quest chapters and recipe/resource datapacks may be required for progression."]
    if archetype == "horror_survival":
        return ["Threat spawn rates and darkness/sound settings should be tuned for pacing."]
    if archetype == "cozy_farming":
        return ["Recipes, crop availability, and village/home goals may need light tuning."]
    return []


def _is_vague_text(text: str) -> bool:
    words = [word for word in re.findall(r"[a-zA-Z]+", text.lower()) if len(word) > 2]
    vague = {"fun", "cool", "lots", "many", "mods", "stuff", "things", "awesome"}
    return len(words) < 6 or sum(1 for word in words if word in vague) >= max(2, len(words) // 3)


def _design_mentions_endgame(design: PackDesign) -> bool:
    text = " ".join(
        [design.summary, *design.required_systems, *design.must_have_experience_beats, *design.quality_bar]
        + [phase.purpose for phase in design.progression_phases]
    ).lower()
    return any(term in text for term in ("endgame", "final", "boss", "mastery", "collection", "replay", "completion"))


def _score_from_design_issues(issues: list[PackDesignReviewIssue]) -> int:
    score = 100
    for issue in issues:
        score -= {"critical": 30, "high": 15, "warning": 6, "info": 0}[issue.severity]
    return max(0, min(100, score))


def _design_next_actions(readiness: str) -> list[str]:
    if readiness == "ready_for_mod_selection":
        return ["run_review_list_against_design", "select_verified_mods"]
    if readiness == "revise_design_first":
        return ["revise_pack_design", "rerun_review_design"]
    return ["add_core_loop", "add_progression_phases", "add_required_systems", "rerun_review_design"]


def _stable_run_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def _candidate_text(candidate: CandidateMod) -> str:
    return " ".join(
        [
            candidate.slug,
            candidate.title,
            candidate.description,
            candidate.body or "",
            " ".join(candidate.categories),
            " ".join(candidate.matched_capabilities),
            " ".join(candidate.why_selected),
        ]
    ).lower()


def _system_covered(system: str, coverage: dict[str, list[str]], design: PackDesign) -> bool:
    aliases = {
        "progression_phases": ("quest_book", "progression_overview", "recipe_progression", "boss_progression"),
        "progression_overview": ("quest_book", "progression_overview"),
        "light_worldgen_or_structures": ("worldgen", "structures"),
        "light_exploration": ("map_tools", "structures", "biome_discovery"),
        "limited_exploration_tools": ("map_tools", "exploration_tools"),
        "large_magic_progression": ("magic_system",),
        "too_much_fast_travel": ("waypoints_or_fast_travel",),
        "brutal_combat": ("combat_overhaul", "boss_progression"),
        "mining_or_underground_loop": ("resource_generation",),
        "core_loop": tuple(),
        "quality_bar": tuple(),
    }
    if system in {"core_loop", "quality_bar"}:
        return bool(design.core_loops if system == "core_loop" else design.quality_bar)
    return bool(coverage.get(system) or any(coverage.get(alias) for alias in aliases.get(system, ())))


def _issue(severity: str, category: str, title: str, detail: str, mods: list[str], action: str, searches: list[str] | None = None) -> ReviewIssue:
    return ReviewIssue(
        severity=severity,
        category=category,
        title=title,
        detail=detail,
        affected_mods=mods,
        suggested_action=action,
        replacement_search_terms=searches or [],
    )


def _anti_goal_issues(design: PackDesign, coverage: dict[str, list[str]]) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    for forbidden in design.forbidden_systems:
        matched = _mods_for_system(forbidden, coverage)
        if matched:
            severity = "high" if forbidden in {"horror_mobs", "hardcore_survival", "overpowered_gear", "full_map_reveal", "tech", "automation"} else "warning"
            issues.append(
                _issue(
                    severity,
                    "design_forbidden_system",
                    f"Forbidden or risky system selected: {forbidden}",
                    f"{design.archetype} design discourages {forbidden}.",
                    matched,
                    "Remove or replace mods that violate the design anti-goals.",
                )
            )
    return issues


def _mods_for_system(system: str, coverage: dict[str, list[str]]) -> list[str]:
    aliases = {
        "large_magic_progression": ["magic_system"],
        "too_much_fast_travel": ["waypoints_or_fast_travel"],
        "brutal_combat": ["combat_overhaul", "boss_progression"],
        "early overpowered gear": ["overpowered_gear"],
        "excessive comfort qol": ["full_map_reveal", "waypoints_or_fast_travel"],
    }
    mods = list(coverage.get(system, []))
    for alias in aliases.get(system, []):
        mods.extend(coverage.get(alias, []))
    return sorted(dict.fromkeys(mods))


def _progression_gap_issues(design: PackDesign, coverage: dict[str, list[str]], missing: list[str]) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    for system in missing:
        severity = "high" if system in {"performance_foundation", "recipe_progression", "storage_solution", "logistics", "quest_book", "skyblock_resource_path"} else "warning"
        issues.append(
            _issue(
                severity,
                "design_required_system",
                f"Missing required design system: {system}",
                f"The {design.archetype} design requires {system}, but selected mods do not cover it.",
                [],
                f"Add a maintained Modrinth mod that covers {system}.",
                [f"{design.loader.title()} {design.minecraft_version} {system.replace('_', ' ')}"],
            )
        )
    if design.archetype in ENDGAME_ARCHETYPES and not coverage.get("endgame_goal") and not coverage.get("boss_progression"):
        issues.append(
            _issue("warning", "endgame_goal", "No selected endgame or replay goal", "The selected list lacks a visible long-term completion, mastery, boss, or final crafting goal.", [], "Add or document an endgame goal.")
        )
    return issues


def _cohesion_issues(
    selected: SelectedModList,
    candidates: list[CandidateMod],
    design: PackDesign,
    coverage: dict[str, list[str]],
    tags_by_slug: dict[str, set[str]],
) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    allowed = set(design.required_systems) | set(design.soft_allowed_systems)
    for pillar in design.pillars:
        allowed.update(pillar.required_capabilities)
    for candidate in candidates:
        tags = tags_by_slug.get(candidate.slug, set())
        reason = " ".join(candidate.why_selected).strip()
        if not tags and len(reason) < 10:
            issues.append(
                _issue(
                    "warning",
                    "mod_role_discipline",
                    "Selected mod has no clear design role",
                    f"{candidate.slug} did not map to a known system tag and has a weak reason_selected.",
                    [candidate.slug],
                    "Justify, replace, or remove this mod.",
                )
            )
        elif allowed and not _has_allowed_role(tags, allowed, design) and candidate.selection_type != "dependency_added":
            issues.append(
                _issue(
                    "warning",
                    "mod_role_discipline",
                    "Selected mod may be off-design",
                    f"{candidate.slug} maps to {', '.join(sorted(tags))}, which is not a clear pillar for {design.archetype}.",
                    [candidate.slug],
                    "Keep only if it supports a named pillar or soft-allowed system.",
                )
            )
    duplicate_groups = {
        "duplicate_quest_systems": ["quest_book"],
        "duplicate_full_combat_overhauls": ["combat_overhaul"],
    }
    for category, systems in duplicate_groups.items():
        mods = sorted({mod for system in systems for mod in coverage.get(system, [])})
        if len(mods) > 1:
            issues.append(_issue("warning", category, "Potential duplicate design system", f"Multiple mods cover {systems[0]}.", mods, "Choose the clearest maintained option."))
    minimaps = sorted(coverage.get("minimap", []))
    world_maps = sorted(coverage.get("world_map", []))
    if len(minimaps) > 1:
        issues.append(_issue("warning", "duplicate_map_tools", "Potential duplicate map tools", "Multiple minimap mods are selected.", minimaps, "Keep one minimap."))
    if len(world_maps) > 1:
        issues.append(_issue("warning", "duplicate_map_tools", "Potential duplicate map tools", "Multiple world map mods are selected.", world_maps, "Keep one world map."))
    base_storage = sorted(coverage.get("base_storage", []))
    if len(base_storage) > 1:
        issues.append(_issue("warning", "duplicate_storage_networks", "Potential duplicate base storage networks", "Multiple base storage network mods are selected.", base_storage, "Keep the clearest base storage network."))
    large_worldgen = sorted(
        candidate.slug
        for candidate in candidates
        if is_large_worldgen_overhaul(candidate, tags_by_slug.get(candidate.slug, set()))
    )
    if len(large_worldgen) >= 2:
        severity = "high" if len(large_worldgen) >= 3 and design.archetype not in {"cozy_farming", "exploration_survival"} else "warning"
        issues.append(
            _issue(
                severity,
                "duplicate_large_worldgen",
                "Multiple large terrain or biome overhauls selected",
                "Large worldgen duplication only counts full terrain/biome overhauls, not village, animal, or light structure mods.",
                large_worldgen,
                "Keep this only if the pack intentionally combines multiple terrain or biome overhauls.",
            )
        )
    if design.archetype not in {"kitchen_sink", "magic_progression", "dark_fantasy"} and len(coverage.get("magic_system", [])) > 1:
        issues.append(_issue("warning", "duplicate_large_magic", "Multiple large magic systems in a focused pack", "Focused non-magic packs usually play better with one clear magic lane.", coverage["magic_system"], "Keep the system that best supports the design."))
    if design.archetype not in {"expert_tech", "tech_automation", "kitchen_sink"} and len(coverage.get("tech", [])) > 1:
        issues.append(_issue("warning", "duplicate_major_tech", "Multiple major tech systems in a non-tech pack", "This risks turning the pack into a tech pile.", coverage["tech"], "Remove tech systems unless the design explicitly allows them."))
    if design.archetype == "vanilla_plus":
        heavy = sorted({mod for system in ("tech", "automation", "magic_system", "boss_progression", "dungeon_progression") for mod in coverage.get(system, [])})
        if len(heavy) >= 2:
            issues.append(_issue("warning", "vanilla_plus_bloat", "Vanilla+ pack is accumulating heavy content systems", "The selected list risks no longer feeling vanilla+.", heavy, "Trim heavy content and keep only subtle systems."))
    return issues


def _has_allowed_role(tags: set[str], allowed: set[str], design: PackDesign) -> bool:
    for tag in tags:
        if tag in allowed or _system_covered(tag, {tag: ["x"]}, design):
            return True
    if "performance_foundation" in tags and "performance_foundation" in design.required_systems:
        return True
    return False


def _pacing_issues(design: PackDesign, coverage: dict[str, list[str]]) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    if (coverage.get("boss_progression") or coverage.get("dungeon_progression")) and not (coverage.get("loot_progression") or coverage.get("gear_upgrade_path")):
        mods = sorted(set(coverage.get("boss_progression", []) + coverage.get("dungeon_progression", [])))
        issues.append(_issue("warning", "pacing_bosses_without_rewards", "Threat progression lacks loot or gear support", "Bosses/dungeons need rewards that change player capability.", mods, "Add loot, gear, or quest progression."))
    if coverage.get("automation") and not (coverage.get("storage_solution") and coverage.get("logistics")):
        issues.append(_issue("warning", "pacing_automation_without_support", "Automation lacks storage/logistics support", "Automation packs become frustrating without item routing and storage.", coverage.get("automation", []), "Add storage and logistics before build."))
    if design.archetype == "expert_tech" and not coverage.get("recipe_progression"):
        issues.append(_issue("high", "expert_tech_recipe_progression", "Expert tech pack has no recipe progression evidence", "Expert packs need recipe changes or explicit gated chains.", coverage.get("tech", []), "Add recipe progression tooling or revise the design."))
    if design.archetype == "skyblock" and (coverage.get("normal_worldgen_dependency") or coverage.get("overworld_structure_dependency")):
        mods = sorted(set(coverage.get("normal_worldgen_dependency", []) + coverage.get("overworld_structure_dependency", [])))
        issues.append(_issue("high", "skyblock_normal_world_dependency", "Skyblock list depends on normal overworld content", "Normal worldgen and structure mods often do nothing or block resources in skyblock.", mods, "Replace with void-compatible resource and quest systems."))
    if design.archetype == "horror_survival":
        comfort = sorted(set(coverage.get("full_map_reveal", []) + coverage.get("waypoints_or_fast_travel", []) + coverage.get("overpowered_gear", [])))
        if comfort:
            issues.append(_issue("warning", "horror_comfort_power_creep", "Horror pacing is weakened by map reveal, fast travel, or overpowered gear", "Horror needs uncertainty and vulnerability.", comfort, "Remove comfort or power-creep systems."))
    if design.archetype == "cozy_farming":
        danger = sorted(set(coverage.get("horror_mobs", []) + coverage.get("hardcore_survival", []) + coverage.get("survival_pressure", [])))
        if danger:
            issues.append(_issue("high", "cozy_danger_pressure", "Cozy pack includes horror or hardcore pressure", "Cozy farming should center home, food, decoration, and gentle goals.", danger, "Remove danger pressure unless the design changes."))
    if design.archetype == "kitchen_sink" and not (coverage.get("quest_book") or coverage.get("progression_overview")):
        issues.append(_issue("warning", "kitchen_sink_no_overview", "Kitchen sink has no quest or progression overview", "Broad packs need a navigation layer for players.", [], "Add quests or explicit progression overview."))
    return issues


def _config_warnings(design: PackDesign, coverage: dict[str, list[str]]) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    if design.config_or_datapack_needs and design.archetype in {"expert_tech", "skyblock", "stoneblock"} and not coverage.get("quest_book"):
        issues.append(
            _issue(
                "warning",
                "config_or_datapack_needed",
                "Design likely needs quests or datapack tuning",
                "; ".join(design.config_or_datapack_needs),
                [],
                "Plan config/datapack work before building.",
            )
        )
    return issues
