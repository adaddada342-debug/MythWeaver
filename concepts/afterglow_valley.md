# Afterglow Valley

Afterglow Valley is a polished cozy exploration and survival modpack for Minecraft 1.20.1 on Fabric. It is about building a beautiful life in a scenic, lightly mysterious world: golden valleys at sunset, warm cottage interiors, riverside paths, windmills, gardens, barns, improved villages, gentle ruins, and long-term settlement projects.

The player should spawn in a gorgeous natural world and feel invited to stay. The core loop is relaxed but durable: explore scenic terrain, gather materials, build and decorate a home, farm and cook, improve storage and travel, discover villages and ruins, collect decorative resources, expand into a beautiful settlement, and keep exploring for inspiration and rare finds.

## Design Pillars

1. Beautiful world worth living in
   - Use one strong scenic worldgen foundation with villages, light structures, wildlife, ambience, particles, and spatial sound.
   - The world should be calm, readable, and inspiring rather than hostile or overloaded.

2. Cozy settlement building
   - Support cottages, bridges, gardens, paths, barns, workshops, kitchens, rooftops, windows, fences, and village restoration.
   - Building variety should come from high-quality complementary block and furniture mods, not random bloat.

3. Chill progression
   - Progression should naturally unlock better food, tools, travel, storage, palettes, and exploration range.
   - Avoid forced grind, large recipe gates, expert automation, and boss-heavy systems.

4. Friendly exploration with light mystery
   - Add scenic journeys, improved villages, modest ruins, landmarks, compasses, maps, and comfortable travel.
   - Danger can exist, but the pack should never become horror, hardcore survival, or stressful combat progression.

5. Stability and proof
   - Use MythWeaver for source resolution, dependency closure, verify-list, Prism instance generation, Fabric/RAM validation, and runtime smoke testing.
   - Do not call the pack stable unless runtime proof exists. If launch automation cannot prove world join, report manual_required honestly.

## Required Systems

- performance_foundation
- beautiful_worldgen
- villages
- light_structures
- cozy_building_blocks
- decoration
- furniture
- farming
- cooking
- animals/wildlife
- ambience
- soundscape
- visual_polish
- map_tools
- compass/discovery tools
- comfortable travel
- backpack/mobile storage
- base storage
- inventory_qol
- client_qol
- light progression
- stable launcher/runtime validation

## Avoid

- horror mobs
- parasite or infection systems
- hardcore thirst, temperature, or survival realism
- brutal combat overhauls
- boss-heavy RPG progression
- Create, Mekanism, Thermal, or similar large tech chains
- guns, explosives, destruction systems
- huge magic systems
- joke or meme mods
- abandoned or low-signal mods
- manual-only sources unless explicitly unavoidable

## Target

- Minecraft: 1.20.1
- Loader: Fabric
- Runtime target: Prism Launcher
- RAM: 8192 MB
- Sources: Modrinth first; CurseForge only through the official API if configured
- Export: Prism instance plus .mrpack where possible
