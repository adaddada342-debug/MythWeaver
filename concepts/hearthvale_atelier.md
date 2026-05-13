# Hearthvale Atelier

## Pack Name

Hearthvale Atelier

## Vibe

A beautiful cozy building and homestead experience for Fabric 1.20.1 focused on warm villages,
cottages, farms, gardens, kitchens, workshops, storage rooms, bridges, roads, and scenic
countryside bases. The tone is calm, inviting, and creative-survival friendly.

## Core Gameplay Loop

Explore gentle terrain for ideal build sites -> gather resources naturally -> expand a cozy base ->
cook and farm -> decorate interiors and pathways -> improve storage and travel convenience -> grow a
small countryside village over time.

## Required Systems

- performance and render foundation
- shader support foundation
- cozy building blocks and decorative sets
- furniture and interior detailing
- farming and cooking progression
- practical storage and inventory QoL
- gentle exploration and village/structure variety
- ambience and visual polish

## Anti-Goals

- heavy industrial tech progression
- combat-overhaul or hardcore survival focus
- horror or oppressive danger-first gameplay
- kitchen-sink mod bloat
- random novelty mods that break aesthetic cohesion
- conflicting worldgen stacks

## Visual Requirements

- Must look beautiful by default in vanilla lighting.
- Must support shaders out of the box.
- Must prioritize cozy architecture readability (wood, stone, lantern-lit interiors, roads, bridges,
  gardens, and village improvements).

## Shader/Iris Requirement

Mandatory rendering stack:

- Sodium
- Iris
- Indium (if required for compatibility)
- Fabric API and required dependencies

If shaderpack auto-install is not safely supported by MythWeaver, produce manual shaderpack setup
instructions instead of faking automatic installation.

## Stability Requirements

- Loader compatibility must be checked before launch.
- If any selected mod requires Fabric Loader >=0.19.2, use 0.19.2 or newer.
- No stable claim without MythWeaver smoke-test proof:
  - `[MythWeaverSmokeTest] PLAYER_JOINED_WORLD`
  - `[MythWeaverSmokeTest] STABLE_60_SECONDS`
