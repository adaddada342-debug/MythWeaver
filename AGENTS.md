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
- Prefer a coherent playable pack over a huge unstable pack.
- Put final artifacts under `output/generated/<pack-name>/`.
