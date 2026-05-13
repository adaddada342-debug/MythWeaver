# Cursor Quick Start

Say `start`.

Cursor should answer:

```text
State your modpack idea.
```

Then give your modpack concept. Cursor should follow `AGENTS.md` and use MythWeaver as the local
deterministic Modrinth/modpack intelligence service.

For multi-source packs, keep the safety boundaries explicit: Modrinth uses the official API,
CurseForge uses the official API with `CURSEFORGE_API_KEY`, Planet Minecraft is manual discovery
only, and direct URLs are blocked by default. Use `source-resolve` before export, and use
`--auto-target` only to negotiate from real metadata, not to force incompatible mods together.

Autopilot V1 can run the private Fabric runtime and safe repair loop, but `verified_playable`
requires MythWeaver smoke-test world-join plus stability markers by default. Client-start or
main-menu log lines are not enough proof. Forge, NeoForge, and Quilt are still unsupported private
runtime targets in V1.
