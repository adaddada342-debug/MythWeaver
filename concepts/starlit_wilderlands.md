# Starlit Wilderlands

## Overview

Starlit Wilderlands is a beautiful vanilla+ Fabric 1.20.1 pack centered on scenic exploration,
ruins discovery, and building a warm frontier base between expeditions. It aims for a polished,
stable-focused experience with light tension at night but no hardcore punishment loops.

The core fantasy is wandering striking terrain, finding villages and ancient-feeling points of
interest, returning home with treasures, and steadily turning a small outpost into a comfortable
lantern-lit settlement.

## Core Fantasy

Discover breathtaking landscapes and subtle adventure content while preserving Minecraft's
recognizable pacing. The pack should feel like "enhanced vanilla exploration" rather than an RPG
overhaul or tech grind.

## Tone

- Crisp natural vistas and atmospheric nights
- Cozy, practical homestead progression
- Gentle danger, not constant dread
- Rewarding exploration and building loops
- Minimal friction in inventory and travel

## Anti-Goals

- Kitchen-sink scale content bloat
- Heavy industrial automation progression
- Hardcore realism systems (thirst/temperature)
- Combat overhaul dependency chains
- Random meme or low-signal novelty mods

## Core Loop

Scout terrain and points of interest -> gather materials and supplies -> improve home base and
storage -> travel further with better navigation and logistics -> keep refining the settlement and
unlocking new build ideas from exploration finds.

## Progression Shape

**Early:** stabilize survival basics, map local area, set a safe base, starter QoL.

**Mid:** improve travel with waystones/backpack, expand building options, explore villages and
structures, deepen storage and organization.

**Late:** polished long-term base with rich decoration, reliable travel network, broad world
coverage, and relaxed "one more trip" exploration gameplay.

## Required Systems

- performance_foundation
- scenic_worldgen
- villages
- light_structures
- cozy_building_blocks
- decoration
- farming_light
- ambience
- soundscape
- visual_polish
- map_tools
- comfortable_travel
- backpack_storage
- base_storage
- inventory_qol
- client_qol

## Selection Rules

- Target Minecraft 1.20.1 on Fabric.
- Prefer Modrinth first; CurseForge only if deterministic flow requires it.
- Keep direct selected mods roughly 35-55 before dependency expansion.
- Prefer maintained, high-signal mods with established compatibility.
- Avoid duplicate systems unless each mod has a clear non-overlapping role.

## Stability Notes

This pack must follow MythWeaver deterministic verification/build flow and only claim `stable` with
runtime smoke-test proof markers:

- `[MythWeaverSmokeTest] PLAYER_JOINED_WORLD`
- `[MythWeaverSmokeTest] STABLE_60_SECONDS`

If those markers are not proven, final status must be `manual_required` or `failed` as appropriate.
