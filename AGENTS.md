# MythWeaver Agent Instructions

When the user opens this folder in Codex, Cursor, or another coding-agent environment and says:

```text
start
```

respond with exactly:

```text
State your modpack idea.
```

After the user gives the idea, do everything from this folder. MythWeaver is a local deterministic
Minecraft modpack intelligence service. You are the external AI orchestrator.

The preferred command is:

```powershell
python -m mythweaver.cli.main generate "<user modpack idea>"
```

Use `--dry-run` first when you want a fast plan/report without downloading jars.

For multi-source work, use source-aware commands explicitly:

```powershell
python -m mythweaver.cli.main source-search "magic" --mc-version 1.20.1 --loader forge --sources modrinth,curseforge
python -m mythweaver.cli.main source-resolve selected_mods.json --sources modrinth,curseforge --target-export curseforge_manifest
python -m mythweaver.cli.main build-from-list selected_mods.json --sources curseforge --target-export curseforge_manifest --loader-version 47.2.0
python -m mythweaver.cli.main build-from-list selected_mods.json --sources modrinth,curseforge --auto-target --target-export prism_instance
```

For Autopilot V1 runtime verification, use:

```powershell
python -m mythweaver.cli.main autopilot selected_mods.json --sources modrinth,curseforge --target-export local_instance --loader fabric
```

Autopilot requires MythWeaver smoke-test proof by default. `verified_playable` means the private
Fabric runtime saw smoke-test world-join and stability markers, not just client-start/main-menu log
lines. Forge, NeoForge, and Quilt still return unsupported runtime issues in the private runtime.

## Required Flow

1. Convert the user idea into a `RequirementProfile`.
2. Prefer `generate_modpack` or `python -m mythweaver.cli.main generate`.
3. Search Modrinth with `search_modrinth`.
4. Verify real project/version/file metadata before selecting any mod.
5. Score candidates with `score_candidates`.
6. Resolve dependencies with `resolve_dependencies`.
7. Detect duplicate functionality with `detect_conflicts`.
8. Build the pack with `build_pack`.
9. Generate safe content with `generate_configs`.
10. Validate launch with `validate_launch` if Prism is configured.
11. If validation fails, call `analyze_failure`, revise the candidate set, and try again.

## Commands

If the `mythweaver` script is not on PATH, use:

```powershell
python -m mythweaver.cli.main start
python -m mythweaver.cli.main tools
python -m mythweaver.cli.main serve
```

To create handoff files from a user idea:

```powershell
python -m mythweaver.cli.main start "A horrifying infinite winter survival world"
```

## Non-Negotiable Rules

- No fake Modrinth projects.
- No guessed download URLs.
- No unverified versions.
- No installing files without hashes.
- Do not scrape CurseForge or Planet Minecraft pages.
- CurseForge requires the official API and `CURSEFORGE_API_KEY`.
- Planet Minecraft is manual discovery only.
- Direct URLs are blocked by default.
- Treat Modrinth `.mrpack`, CurseForge manifest, Prism instance, and local instance as different export targets.
- Do not call Autopilot packs verified unless smoke-test proof is present or the user explicitly chose a weaker manual diagnostic mode.
- Prefer a coherent playable pack over a huge unstable pack.
- Put final artifacts under `output/generated/<pack-name>/`.
